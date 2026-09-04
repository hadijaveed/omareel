#!/usr/bin/env python3
"""Fresh-machine fixtures: no desktop, camera, cloud, or user settings changed."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("system_check", ROOT / "bin/system-check.py")
system = importlib.util.module_from_spec(spec)
spec.loader.exec_module(system)


class CameraTests(unittest.TestCase):
    def test_four_three_camera_uses_its_advertised_mode(self):
        mode = system.choose_camera("[0]: 'YUYV'\nSize: Discrete 640x480\nInterval: Discrete 0.040s (25.000 fps)")
        self.assertEqual(mode, dict(format="yuyv422", width=640, height=480, fps=25))

    def test_resolution_never_leaks_between_pixel_formats(self):
        mode = system.choose_camera("[0]: 'MJPG'\nSize: Discrete 640x480\nInterval: Discrete 0.033s (30.000 fps)\n[1]: 'YUYV'\nSize: Discrete 1280x720\nInterval: Discrete 0.067s (15.000 fps)")
        self.assertEqual((mode["format"], mode["width"], mode["fps"]), ("mjpeg", 640, 30))

    def test_fractional_fps_and_high_only_fps_are_preserved(self):
        for fps in (29.97, 60):
            self.assertEqual(system.choose_camera(f"[0]: 'MJPG'\nSize: Discrete 1280x720\nInterval: Discrete 0.033s ({fps} fps)")["fps"], fps)

    def test_unknown_and_stepwise_modes_fail_with_guidance(self):
        for listing in ("", "[0]: 'MJPG'\nSize: Stepwise 1x1 - 4096x4096\nInterval: Discrete 0.033s (30 fps)", "[0]: 'H264'\nSize: Discrete 640x480\nInterval: Discrete 0.033s (30 fps)"):
            with self.assertRaisesRegex(ValueError, "turn Camera off"):
                system.choose_camera(listing)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="omareel-setup-test-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.config = self.path / "config.json"
        self.config.write_text(json.dumps(dict(outputDir=str(self.path), mic=False, webcam=False, denoise=False)))
        self.env = dict(os.environ, OMAREEL_CONFIG=str(self.config), XDG_RUNTIME_DIR=str(self.path))
        self.env.pop("OMAREEL_OPERATION_LOCKED", None)

    def shell(self, command):
        return subprocess.run(["bash", "-c", 'source "$1"; omarchy-shell(){ :; }; notify(){ :; }; ' + command,
                               "_", str(ROOT / "bin/omareel")], env=self.env, capture_output=True, text=True, timeout=10)

    def test_stalled_start_is_error_not_success(self):
        result = self.shell('''compatibility_report(){ echo '{"ready":true}'; }; gsr_running(){ return 1; };
audio_sources(){ :; }; sleep(){ :; }; gpu-screen-recorder(){ /usr/bin/sleep 0.8; };
cmd_start area --region=100x100+0+0 --no-mic --no-webcam; result=$?; wait;
echo "start_exit=$result"; cat "$STATE_FILE"''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("start_exit=1", result.stdout)
        state = json.loads((self.path / "omareel/state.json").read_text())
        self.assertEqual(state["phase"], "error")
        self.assertIn("No video", state["error"])

    def test_failed_preflight_never_launches_capture(self):
        result = self.shell('''compatibility_report(){ echo '{"errors":["Missing test tool"]}'; return 1; };
gpu-screen-recorder(){ echo SHOULD_NOT_RUN; }; cmd_start area''')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("SHOULD_NOT_RUN", result.stdout)
        self.assertEqual(json.loads((self.path / "omareel/state.json").read_text())["error"], "Missing test tool")

    def test_legacy_microphone_settings_do_not_change_system_volume(self):
        self.config.write_text('{"micVolumePercent":80}')
        result = self.shell('pactl(){ echo UNEXPECTED_MUTATION; }; prepare_mic_source default_input')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_opt_in_volume_never_unmutes(self):
        self.config.write_text('{"manageMicVolume":true,"micVolumePercent":70}')
        result = self.shell('pactl(){ echo "$*" >&2; }; prepare_mic_source default_input; tail -1 "$LOG_FILE"')
        self.assertEqual(result.returncode, 0)
        self.assertIn("70%", result.stdout)
        # Assert the actual argument sequence separately from suppressed output.
        result = self.shell('pactl(){ printf "%s\\n" "$*" >"$RUNTIME_DIR/pactl-call"; }; prepare_mic_source default_input; cat "$RUNTIME_DIR/pactl-call"')
        self.assertEqual(result.stdout.strip(), "set-source-volume @DEFAULT_SOURCE@ 70%")

    def test_invalid_existing_model_is_not_selected(self):
        (self.path / "bd.rnnn").write_text("partial download")
        result = self.shell('MODEL_DIR="$XDG_RUNTIME_DIR"; model_path bd')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_link_never_overwrites_an_existing_command(self):
        target = self.path / "omareel"
        target.write_text("belongs to someone else")
        result = self.shell('link_cli "$XDG_RUNTIME_DIR/omareel"')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), "belongs to someone else")

    def test_invalid_settings_are_not_replaced(self):
        self.config.write_text("broken JSON")
        result = subprocess.run([str(ROOT / "bin/omareel"), "status"], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid settings JSON", result.stderr)
        self.assertEqual(self.config.read_text(), "broken JSON")

    def test_verified_model_download_is_atomic_and_retry_is_idempotent(self):
        data = b"fixture model"
        entry = {"test": ("fixture.rnnn", hashlib.sha256(data).hexdigest())}
        with patch.object(system, "MODELS", entry), patch.object(system, "urlopen", side_effect=lambda *a, **k: io.BytesIO(data)) as fetch:
            self.assertEqual(system.install_models(self.path), 0)
            self.assertEqual(system.install_models(self.path), 0)
            self.assertEqual(fetch.call_count, 1)
        self.assertEqual((self.path / "test.rnnn").read_bytes(), data)
        self.assertFalse(list(self.path.glob(".model-*")))

    def test_corrupt_download_never_replaces_existing_model(self):
        target = self.path / "test.rnnn"
        target.write_bytes(b"previous version")
        with patch.object(system, "MODELS", {"test": ("test.rnnn", "0"*64)}), patch.object(system, "urlopen", side_effect=lambda *a, **k: io.BytesIO(b"corrupt")):
            self.assertEqual(system.install_models(self.path), 1)
        self.assertEqual(target.read_bytes(), b"previous version")

    def test_offline_model_setup_fails_without_removing_previous_file(self):
        with patch.object(system, "MODELS", {"test": ("test.rnnn", "0"*64)}), patch.object(system, "urlopen", side_effect=OSError("offline")):
            self.assertEqual(system.install_models(self.path), 1)

    def fake_probe(self, args, **kwargs):
        if args[0] == "omarchy": return 0, "4.0.1"
        if args[0] == "hyprctl": return 0, '[{"name":"eDP-1"}]'
        if "--help" in args: return 0, "-fallback-cpu-encoding -fm -cursor"
        if "-filters" in args: return 0, "\n".join(" ... " + name + " A->A" for name in ("aformat", "afade", "volume", "amix", "anull", "asetpts"))
        if "-encoders" in args: return 0, "libx264 aac"
        return 0, ""

    def report(self, missing=(), **config):
        with patch.object(system.shutil, "which", side_effect=lambda name: None if name in missing else "/usr/bin/"+name), patch.object(system, "run", side_effect=self.fake_probe), patch.dict(os.environ, {"WAYLAND_DISPLAY":"test", "XDG_RUNTIME_DIR":self.tmp.name}):
            return system.readiness(dict(outputDir=self.tmp.name, mic=False, webcam=False, denoise=False, **config))

    def test_screen_only_setup_does_not_require_camera_tools(self):
        self.assertTrue(self.report(missing=("mpv", "v4l2-ctl", "rclone"))["ready"])

    def test_missing_core_tools_block_readiness(self):
        report = self.report(missing=("python3", "ffmpeg", "flock"))
        self.assertFalse(report["ready"])
        self.assertEqual(set(report["missing"]), {"python3", "ffmpeg", "flock"})

    def test_ffmpeg_nine_two_column_filter_listing(self):
        old = self.fake_probe
        def modern(args, **kwargs):
            code, out = old(args, **kwargs)
            return code, out.replace(" ... ", " .. ")
        with patch.object(self, "fake_probe", side_effect=modern):
            self.assertTrue(self.report()["ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
