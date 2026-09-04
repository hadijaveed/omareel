#!/usr/bin/env python3
"""Bounded, read-only readiness probes and camera negotiation; stdlib only."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlopen

MODEL_REV = "3eee541a283fd3b8f81b85b1748e3b9ccbefa04d"
MODELS = {
    "bd": ("beguiling-drafter-2018-08-30/bd.rnnn", "ae3f7411e1e6a884f839a4a145c394408398f09854dbc1216ee02faafc98a17b"),
    "sh": ("somnolent-hogwash-2018-09-01/sh.rnnn", "70bb6685eb0c2a1d18e2918dca3fbfbd39317010b1802eb1b6ea73a92f3fdec0"),
}


def run(args, timeout=5):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.TimeoutExpired):
        return 1, "Command unavailable or timed out"


def camera_modes(text):
    """Keep format/size/fps together; never borrow a size from another format."""
    formats = {"MJPG": "mjpeg", "JPEG": "mjpeg", "YUYV": "yuyv422",
               "UYVY": "uyvy422", "NV12": "nv12", "YU12": "yuv420p",
               "RGB3": "rgb24", "BGR3": "bgr24", "GREY": "gray"}
    fmt, size, modes = None, None, []
    for line in text.splitlines():
        match = re.search(r"\[\d+\]:\s*'([^']+)'", line)
        if match:
            fmt, size = formats.get(match[1]), None
        match = re.search(r"Size:\s*Discrete\s+(\d+)x(\d+)", line)
        if match:
            size = tuple(map(int, match.groups()))
        elif "Size:" in line:
            size = None
        match = re.search(r"Interval:\s*Discrete.*\(([\d.]+) fps\)", line)
        if fmt and size and match and float(match[1]) > 0:
            w, h = size
            if w > 0 and h > 0 and w % 2 == h % 2 == 0:
                modes.append((fmt, w, h, float(match[1])))
    return modes


def choose_camera(text):
    modes = camera_modes(text)
    if not modes:
        raise ValueError("Camera exposes no supported discrete video modes. Choose another camera or turn Camera off.")
    def score(m):
        fmt, w, h, fps = m
        # Prefer colour, <=720p/30 fps, then a healthy frame rate and detail.
        return (fmt == "gray", w*h > 1280*720, fps > 30.1,
                fps < 24, abs(w*h - 1280*720), fmt != "mjpeg", abs(fps - 30))
    fmt, w, h, fps = min(modes, key=score)
    return {"format": fmt, "width": w, "height": h, "fps": fps}


def readiness(config, kind="area", probe_gpu=False):
    errors, warnings = [], []
    required = ["gpu-screen-recorder", "ffmpeg", "ffprobe", "jq", "flock", "timeout",
                "python3", "hyprctl", "omarchy-shell", "wl-copy", "xdg-open", "sha256sum"]
    if kind in ("area", "window"):
        required += ["slurp", "omarchy-capture-region"]
    if kind == "screen":
        required += ["omarchy-hyprland-monitor-focused"]
    if config.get("mic", True) or config.get("desktopAudio", False):
        required += ["pactl"]
    if config.get("webcam", False):
        required += ["mpv", "v4l2-ctl", "fuser", "omarchy-capture-webcam-list"]
    missing = [dep for dep in required if not shutil.which(dep)]
    if missing:
        errors.append("Missing tools: " + ", ".join(missing) + ". See README → Requirements.")
    if not os.environ.get("XDG_RUNTIME_DIR") or not os.environ.get("WAYLAND_DISPLAY"):
        errors.append("Open Omareel inside your Omarchy Wayland desktop session.")
    if shutil.which("omarchy"):
        code, version = run(["omarchy", "version"])
        match = re.search(r"(\d+)\.(\d+)", version)
        if code or not match or int(match[1]) < 4:
            errors.append("Omareel requires Omarchy 4 with the Quickshell plugin system.")
    else:
        errors.append("Omarchy 4 is required; this is not a standalone desktop application.")
    if "hyprctl" not in missing:
        code, monitors = run(["hyprctl", "-j", "monitors"])
        try:
            connected = json.loads(monitors)
        except ValueError:
            connected = []
        if code or not isinstance(connected, list) or not connected:
            errors.append("Cannot reach a Hyprland monitor. Reopen from the desktop session.")
    if "gpu-screen-recorder" not in missing:
        _, help_text = run(["gpu-screen-recorder", "--help"])
        flags = ["-fallback-cpu-encoding", "-fm", "-cursor"]
        if kind == "window" and config.get("windowCaptureMode") == "portal":
            flags += ["-restore-portal-session"]
        if any(flag not in help_text for flag in flags):
            errors.append("gpu-screen-recorder lacks required options. Update the Omarchy packages.")
    if "ffmpeg" not in missing:
        _, filters = run(["ffmpeg", "-hide_banner", "-filters"])
        # FFmpeg 9 prints two capability columns; older releases print three.
        names = set(re.findall(r"^\s*[.A-Z|]{2,3}\s+(\w+)\s", filters, re.M))
        needed = {"aformat", "afade", "volume", "amix", "anull", "asetpts"}
        if config.get("denoise", True) and config.get("mic", True):
            needed |= {"afftdn", "highpass", "agate", "loudnorm", "alimiter", "acompressor"}
        if config.get("webcam", False):
            needed |= {"scale", "crop", "format", "alphamerge", "geq", "overlay", "movie"}
        if needed - names:
            errors.append("FFmpeg is missing filters: " + ", ".join(sorted(needed - names)))
        _, encoders = run(["ffmpeg", "-hide_banner", "-encoders"])
        if not re.search(r"\blibx264\b", encoders) or not re.search(r"\baac\b", encoders):
            errors.append("Install FFmpeg with libx264 and AAC encoders for camera/export support.")
    if config.get("mic", True) and "pactl" not in missing:
        source = config.get("micDevice", "default")
        if source in ("default", "default_input", ""):
            code, source = run(["pactl", "get-default-source"])
            source = source.strip()
        code, muted = run(["pactl", "get-source-mute", source])
        if code:
            warnings.append("Selected microphone is unavailable; recording will try the system default.")
            _, fallback = run(["pactl", "get-default-source"])
            code, muted = run(["pactl", "get-source-mute", fallback.strip()])
            if code:
                errors.append("No usable microphone found. Connect a microphone or turn Microphone off.")
        if not code and "yes" in muted.lower():
            errors.append("Your microphone is muted in system audio. Unmute it or turn Microphone off.")
    if config.get("webcam", False) and not any(dep in missing for dep in ("v4l2-ctl", "omarchy-capture-webcam-list")):
        device = str(config.get("webcamDevice", "auto"))
        if device in ("auto", ""):
            _, listing = run(["omarchy-capture-webcam-list"])
            rows = [line for line in listing.splitlines() if line.startswith("/dev/video") and "loopback" not in line.lower()]
            device = rows[0].split()[0] if rows else ""
        if not device.startswith("/dev/video") or not os.path.exists(device):
            errors.append("Selected camera is unavailable. Reconnect it, choose another camera, or turn Camera off.")
        else:
            code, listing = run(["v4l2-ctl", "--list-formats-ext", "-d", device])
            try:
                if code:
                    raise ValueError("Cannot read camera capabilities. Check device permissions or close the app using it.")
                choose_camera(listing)
            except ValueError as exc:
                errors.append(str(exc))
    output = Path(str(config.get("outputDir", "~/Videos/Omareel"))).expanduser()
    existing = output
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if not existing.is_dir() or not os.access(existing, os.W_OK):
        errors.append("Recording folder is not writable. Choose another output folder.")
    else:
        try:
            if shutil.disk_usage(existing).free < 512 * 1024 * 1024:
                errors.append("Less than 512 MB free in the recording folder. Free space before recording.")
        except OSError:
            errors.append("Cannot check recording storage. Reconnect the drive or choose another folder.")
    if probe_gpu and "gpu-screen-recorder" not in missing:
        code, info = run(["gpu-screen-recorder", "--info"], timeout=8)
        if code:
            errors.append("GPU capture probe failed. Check graphics drivers and capture permissions; run gpu-screen-recorder --info.")
        else:
            warnings.append("GPU information probe passed; a short real recording is still required on this laptop.")
    return {"ready": not errors, "errors": errors, "warnings": warnings, "missing": missing}


def install_models(directory):
    directory.mkdir(parents=True, exist_ok=True)
    success = True
    for name, (relative, digest) in MODELS.items():
        target = directory / (name + ".rnnn")
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            print("ok       verified model " + name)
            continue
        installed = False
        for attempt in range(2):
            temporary = None
            try:
                with urlopen("https://raw.githubusercontent.com/GregorR/rnnoise-models/" + MODEL_REV + "/" + relative, timeout=15) as response:
                    data = response.read(2 * 1024 * 1024)
                if hashlib.sha256(data).hexdigest() != digest:
                    raise ValueError("checksum mismatch")
                with tempfile.NamedTemporaryFile(dir=directory, prefix=".model-", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(target)
                print("fetched  verified model " + name)
                installed = True
                break
            except (OSError, ValueError) as exc:
                if attempt == 1:
                    print("FAILED   model " + name + ": " + str(exc), file=sys.stderr)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        success = success and installed
    return 0 if success else 1


def main():
    if sys.argv[1] == "camera":
        print(json.dumps(choose_camera(sys.stdin.read())))
    elif sys.argv[1] == "models":
        return install_models(Path(sys.argv[2]))
    else:
        config = json.loads(Path(sys.argv[2]).read_text())
        if not isinstance(config, dict):
            raise ValueError("Settings must be a JSON object")
        # CLI overrides reflect the actual take, not stale saved settings.
        for arg in sys.argv[4:]:
            if arg in ("--no-mic", "--no-webcam", "--no-denoise", "--no-desktop-audio"):
                config[{"--no-mic": "mic", "--no-webcam": "webcam", "--no-denoise": "denoise", "--no-desktop-audio": "desktopAudio"}[arg]] = False
            if arg in ("--mic", "--webcam", "--desktop-audio"):
                config[{"--mic": "mic", "--webcam": "webcam", "--desktop-audio": "desktopAudio"}[arg]] = True
        report = readiness(config, sys.argv[3], "--probe-gpu" in sys.argv)
        print(json.dumps(report))
        return 0 if report["ready"] else 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, IndexError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
