#!/usr/bin/env python3
"""Non-destructive, local-only Studio finishing. Python stdlib + FFmpeg.

One geometry/filter path for frame previews and exports. Capture and audio
cleanup deliberately live elsewhere. No shell, remote images, or overwrite.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import sys
import tempfile
import uuid
import zlib

DEFAULTS = dict(preset="midnight", background="midnight", image="", color="#20242f",
                padding="normal", frame="rounded", shadow=True, aspect="original",
                fit="fit", zoom="1", focus="center", zooms=[], previewTime=0)
PRESETS = {
    "midnight": dict(background="midnight", frame="rounded", shadow=True, padding="normal"),
    "paper": dict(background="paper", frame="application", shadow=True, padding="normal"),
    "minimal": dict(background="solid", color="#20242f", frame="none", shadow=False, padding="small"),
}
CHOICES = dict(preset=(*PRESETS, "custom"), background=("midnight", "paper", "solid", "image"),
               padding=("small", "normal", "large"), frame=("none", "rounded", "application"),
               aspect=("original", "landscape", "square", "portrait"), fit=("fit", "fill"),
               zoom=("1", "1.25", "1.5"), focus=("center", "top-left", "top-center", "top-right",
               "center-left", "center-right", "bottom-left", "bottom-center", "bottom-right"))


def options(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Invalid Studio settings. Reset the style and try again.")
    result = DEFAULTS | PRESETS.get(value.get("preset", "midnight"), {}) | value
    for key, allowed in CHOICES.items():
        if result[key] not in allowed:
            raise ValueError("Invalid Studio " + key)
    if not isinstance(result["shadow"], bool):
        raise ValueError("Shadow must be on or off")
    if not isinstance(result["color"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", result["color"]):
        raise ValueError("Use a six-digit color such as #20242f")
    if not isinstance(result["image"], str):
        raise ValueError("Choose a local PNG, JPEG or WebP image")
    def number(value):
        return type(value) in (int, float) and math.isfinite(value)
    if not number(result["previewTime"]) or not 0 <= result["previewTime"] < 86400:
        raise ValueError("Choose a preview time within the recording")
    if not isinstance(result["zooms"], list) or len(result["zooms"]) > 8:
        raise ValueError("Use up to eight manual zooms")
    end = 0
    for event in result["zooms"]:
        if (not isinstance(event, dict) or set(event) != {"start", "end", "amount", "x", "y"}
                or not all(number(v) for v in event.values())
                or not end <= event["start"] < event["end"] < 86400
                or event["end"] - event["start"] < .5
                or not 1.1 <= event["amount"] <= 2
                or not 0 <= event["x"] <= 1 or not 0 <= event["y"] <= 1):
            raise ValueError("Zooms need non-overlapping time ranges of at least 0.5 seconds and a point inside the picture")
        end = event["end"]
    return result


def zoom_expressions(events):
    """The same timestamp expressions drive preview and export."""
    z, x, y = "1", "0.5", "0.5"
    for event in events:
        start, end = event["start"], event["end"]
        ramp = min(.35, (end-start)/3)
        phase = f"min(clip((in_time-{start})/{ramp},0,1),clip(({end}-in_time)/{ramp},0,1))"
        eased = f"(({phase})*({phase})*(3-2*({phase})))"
        condition = f"between(in_time,{start},{end})"
        z = f"if({condition},1+{event['amount']-1}*{eased},{z})"
        # This anchor stays at its relative screen position during the zoom,
        # avoiding the initial sideways jump of a clamped centered crop.
        x = f"if({condition},{event['x']},{x})"
        y = f"if({condition},{event['y']},{y})"
    return z, f"(iw-iw/zoom)*({x})", f"(ih-ih/zoom)*({y})"


def local_file(value):
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("Choose a regular local file")
    return path


def run(args, timeout=None):
    # Children are reaped on cancellation, including FFmpeg's encoder workers.
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as child:
        try:
            stdout, stderr = child.communicate(timeout=timeout)
        except BaseException:
            child.terminate()
            try:
                child.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate()
            raise
    if child.returncode:
        raise ValueError(stderr.decode(errors="replace")[-1800:].strip() or "Studio render failed")
    return stdout


def probe(path):
    data = json.loads(run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
                           "-f", "mov", "-show_streams", "-show_format", "-of", "json", str(path)], 15))
    video = next((s for s in data["streams"] if s["codec_type"] == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
    if not video:
        raise ValueError("This file has no video track")
    if video.get("color_transfer") in ("smpte2084", "arib-std-b67"):
        raise ValueError("Studio currently supports SDR recordings. Keep this HDR video as the original.")
    width, height = video["width"], video["height"]
    sar = video.get("sample_aspect_ratio", "1:1")
    if sar not in ("N/A", "0:1"):
        num, den = map(int, sar.split(":"))
        width = round(width * num / den)
    rotation = next((s["rotation"] for s in video.get("side_data_list", []) if "rotation" in s), 0)
    if abs(rotation) % 180 == 90:
        width, height = height, width
    num, den = map(int, video.get("avg_frame_rate", "30/1").split("/"))
    fps = num / den if den and num else 30
    duration = float(data["format"].get("duration", 0))
    if min(width, height) < 16 or max(width, height) > 16384 or not 0 < duration < 86400:
        raise ValueError("Unsupported video dimensions or duration")
    return dict(width=width, height=height, fps=min(120, max(1, fps)), duration=duration)


def even(value):
    return max(2, int(value) // 2 * 2)


def geometry(info, opts):
    sw, sh = info["width"], info["height"]
    ratio = {"original": sw / sh, "landscape": 16 / 9, "square": 1, "portrait": 9 / 16}[opts["aspect"]]
    # Keep the original long edge, capped at 3840; never promise extra detail.
    edge = min(3840, max(sw, sh))
    w, h = (even(edge), even(edge / ratio)) if ratio >= 1 else (even(edge * ratio), even(edge))
    if min(w, h) < 64:
        raise ValueError("This canvas is too narrow for Studio. Choose a different canvas or use the original.")
    pad = even(min(w, h) * {"small": .035, "normal": .065, "large": .10}[opts["padding"]])
    bar = even(min(w, h) * .035) if opts["frame"] == "application" else 0
    aw, ah = w - pad * 2, h - pad * 2 - bar
    cw, ch = sw / float(opts["zoom"]), sh / float(opts["zoom"])
    if opts["fit"] == "fill":
        if cw / ch > aw / ah:
            cw = ch * aw / ah
        else:
            ch = cw * ah / aw
    cw, ch = even(cw), even(ch)
    scale = min(aw / cw, ah / ch)
    vw, vh = even(cw * scale), even(ch * scale)
    focus = opts["focus"]
    fx = 0 if "left" in focus else 1 if "right" in focus else .5
    fy = 0 if "top" in focus else 1 if "bottom" in focus else .5
    return dict(w=w, h=h, vw=vw, vh=vh, x=(w-vw)//2, y=(h-vh-bar)//2+bar,
                bar=bar, cw=cw, ch=ch, cx=int((sw-cw)*fx), cy=int((sh-ch)*fy),
                radius=even(min(vw, vh)*.025) if opts["frame"] != "none" else 0)


def png(path, w, h, rows, color_type):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = b"".join(b"\0" + row for row in rows)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 3)) + chunk(b"IEND", b""))


def inset(y, height, radius):
    if not radius:
        return 0
    distance = max(radius - y - .5, y - (height - radius) + .5, 0)
    return round(radius - math.sqrt(max(0, radius*radius - distance*distance)))


def rounded_row(width, height, radius, y):
    """Four vertical samples and horizontal pixel coverage for smooth corners."""
    if not radius:
        return b"\xff" * width
    cuts = []
    for sample in range(4):
        py = y + (sample + .5) / 4
        distance = max(radius - py, py - (height - radius), 0)
        cuts.append(radius - math.sqrt(max(0, radius * radius - distance * distance)))
    edge = min(width // 2, math.ceil(max(cuts)))
    left = bytes(round(255 * sum(min(1, max(0, x + 1 - cut)) for cut in cuts) / 4)
                 for x in range(edge))
    return left + b"\xff" * (width - edge * 2) + left[::-1]


def assets(directory, geo, opts):
    w, h, vw, vh = (geo[k] for k in ("w", "h", "vw", "vh"))
    bg, decor, mask = (directory / name for name in ("background.png", "decoration.png", "mask.png"))
    if opts["background"] == "image":
        source = local_file(opts["image"])
        with source.open("rb") as stream:
            magic = stream.read(12)
        codec = "png" if magic.startswith(b"\x89PNG\r\n\x1a\n") else "mjpeg" if magic.startswith(b"\xff\xd8\xff") else (
            "webp" if magic.startswith(b"RIFF") and magic[8:12] == b"WEBP" else "")
        if not codec or source.stat().st_size > 50 * 1024 * 1024:
            raise ValueError("Background must be a local PNG, JPEG or WebP, up to 50 MB")
        run(["ffmpeg", "-v", "error", "-nostdin", "-protocol_whitelist", "file,pipe", "-f", "image2",
             "-pattern_type", "none", "-c:v", codec, "-max_pixels", "40000000", "-threads", "2", "-i", str(source), "-vf",
             f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1",
             "-frames:v", "1", "-threads", "2", str(bg)], 30)
    else:
        colors = {"midnight": ((57, 65, 106), (17, 24, 39)), "paper": ((240, 229, 212), (197, 210, 208))}
        solid = tuple(bytes.fromhex(opts["color"][1:]))
        top, bottom = colors.get(opts["background"], (solid, solid))
        png(bg, w, h, (bytes(round(a+(b-a)*y/max(1,h-1)) for a,b in zip(top,bottom))*w for y in range(h)), 2)
    rows = [bytearray(w*4) for _ in range(h)]

    def rect(x, y, rw, rh, radius, rgba):
        for line in range(max(0,y), min(h,y+rh)):
            coverage = rounded_row(rw, rh, radius, line-y)
            left, right = max(0,x), min(w,x+rw)
            if right > left:
                pixels = bytearray(bytes(rgba) * (right-left))
                pixels[3::4] = bytes(round(a * rgba[3] / 255) for a in coverage[left-x:right-x])
                rows[line][left*4:right*4] = pixels

    x, y, bar, radius = (geo[k] for k in ("x", "y", "bar", "radius"))
    if opts["shadow"]:
        # Blur one silhouette once. Leave room for its falloff inside the canvas.
        margin = min(x, w-x-vw, y-bar, h-y-vh)
        sigma = max(.5, min(min(w,h) * .012, margin / 4))
        offset = max(1, round(sigma * .6))
        rect(x, y-bar+offset, vw, vh+bar, radius, (0,0,0,65))
        seed = directory / "shadow-seed.png"
        shadow = directory / "shadow.png"
        png(seed, w, h, rows, 6)
        run(["ffmpeg", "-v", "error", "-nostdin", "-threads", "2", "-i", str(seed),
             "-vf", f"format=gbrap,gblur=sigma={sigma:.4f}:steps=3,format=rgba",
             "-frames:v", "1", "-threads", "2", str(shadow)], 30)
        rows = [bytearray(w*4) for _ in range(h)]
    if bar:
        rect(x, y-bar, vw, vh+bar, radius, (34,37,45,255))
        for i, color in enumerate(((231,112,107,255),(232,193,102,255),(128,180,140,255))):
            size = max(2,bar//4)
            rect(x+bar//2+i*size*2, y-bar+(bar-size)//2, size, size, size//2, color)
    png(decor, w, h, rows, 6)
    if opts["shadow"]:
        combined = directory / "frame-shadow.png"
        run(["ffmpeg", "-v", "error", "-nostdin", "-filter_complex_threads", "2",
             "-i", str(shadow), "-i", str(decor), "-filter_complex", "overlay=format=auto",
             "-frames:v", "1", "-threads", "2", str(combined)], 30)
        decor = combined
    png(mask, vw, vh, (rounded_row(vw, vh, radius if not bar or line>vh//2 else 0, line)
                       for line in range(vh)), 0)
    return bg, decor, mask


def render(source, opts, directory, preview=False):
    source = local_file(source)
    info = probe(source)
    if any(e["end"] > info["duration"] + .001 for e in opts["zooms"]):
        raise ValueError("A zoom ends after this recording. Adjust its time range.")
    if preview and opts["previewTime"] >= info["duration"]:
        raise ValueError("Choose a preview time before the end of the recording")
    geo = geometry(info, opts)
    geo["duration"] = info["duration"]
    bg, decor, mask = assets(directory, geo, opts)
    w,h,vw,vh,x,y,cw,ch,cx,cy = (geo[k] for k in ("w","h","vw","vh","x","y","cw","ch","cx","cy"))
    sw, sh = info["width"], info["height"]
    # Background is looped at the source rate; screen EOF ends video output.
    screen = f"scale={vw}:{vh}:flags=lanczos"
    if opts["zooms"]:
        z, zx, zy = zoom_expressions(opts["zooms"])
        start = opts["previewTime"] if preview else 0
        screen = (f"setpts=PTS-STARTPTS+{start}/TB,fps={info['fps']},format=yuv444p,"
                  f"zoompan=z='{z}':x='{zx}':y='{zy}':d=1:s={vw}x{vh}:fps={info['fps']},"
                  "setpts=PTS-STARTPTS")
    graph = (f"[0:v:0]scale={sw}:{sh},setsar=1,crop={cw}:{ch}:{cx}:{cy},{screen},format=rgb24[screen];"
             "[screen][3:v]alphamerge[rounded];"
             "[1:v][2:v]overlay=format=auto[backdrop];"
             f"[backdrop][rounded]overlay={x}:{y}:shortest=1:format=auto,format=yuv420p")
    if preview:
        graph += ",scale=960:640:force_original_aspect_ratio=decrease"
    graph += "[out]"
    target = directory / ("preview.png" if preview else "render.mp4")
    command = ["ffmpeg", "-v", "error", "-nostdin", "-filter_complex_threads", "2"]
    if preview:
        command += ["-ss", str(opts["previewTime"])]
    command += [
               "-protocol_whitelist", "file,pipe", "-f", "mov", "-threads", "2", "-i", str(source),
               "-loop", "1", "-framerate", str(info["fps"]), "-i", str(bg), "-i", str(decor), "-i", str(mask),
               "-filter_complex", graph, "-map", "[out]"]
    if preview:
        command += ["-frames:v", "1", "-threads", "2"]
    else:
        command += ["-map", "0:a?", "-c:a", "copy", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-threads", "2", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-t", str(info["duration"])]
    run(command + [str(target)], 60 if preview else None)
    return target, geo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preview", "export", "defaults"))
    parser.add_argument("source", nargs="?")
    parser.add_argument("settings", nargs="?", default="{}")
    args = parser.parse_args()
    if args.action == "defaults":
        print(json.dumps(DEFAULTS))
        return
    source = local_file(args.source)
    opts = options(json.loads(args.settings))
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "omareel"
    runtime.mkdir(exist_ok=True, parents=True)
    # Exports stage on the destination filesystem. A completed file appears
    # atomically under a new UUID, never replacing the input or another export.
    parent = runtime if args.action == "preview" else source.parent
    with tempfile.TemporaryDirectory(prefix=".omareel-studio-", dir=parent) as temp:
        result, geo = render(source, opts, Path(temp), args.action == "preview")
        name = "studio-preview-" + uuid.uuid4().hex + ".png" if args.action == "preview" else str(uuid.uuid4()) + ".mp4"
        dest = parent / name
        os.link(result, dest)  # Fails rather than overwriting even a UUID collision.
        os.chmod(dest, 0o600)
        if args.action == "preview":
            # Bound disposable previews; never touch recordings or arbitrary paths.
            previews = sorted((p for p in runtime.glob("studio-preview-*.png")
                               if re.fullmatch(r"studio-preview-[0-9a-f]{32}\.png", p.name)
                               and not p.is_symlink()), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in previews[8:]:
                old.unlink(missing_ok=True)
        print(json.dumps(dict(file=str(dest), original=str(source), width=geo["w"], height=geo["h"],
                             duration=geo["duration"], picture={k: geo[k] for k in ("x", "y", "vw", "vh")}, options=opts)))


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(130))
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print("Studio: " + str(error), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
