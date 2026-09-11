#!/usr/bin/env python3
"""Settings attack fixtures and Stop recovery; no real devices or cloud access."""
import contextlib
import importlib
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
sys.path.insert(0, str(ROOT / "bin"))
from settings import Settings
upload = importlib.import_module("upload-config")


class SettingsSecurity(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="omareel-settings-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / "config.json"
        self.config.write_text('{"mic":false,"webcamCorner":"top-right"}')
        self.victim = self.root / "untouched"
        self.victim.write_text("unrelated contents")
        self.env = dict(os.environ, XDG_RUNTIME_DIR=str(self.root), OMAREEL_CONFIG=str(self.config))
        self.env.pop("OMAREEL_OPERATION_LOCKED", None)
        mock = self.root / "mockbin"
        mock.mkdir()
        for name in ("omarchy-shell", "omarchy-notification-send", "notify-send", "wl-copy"):
            script = mock / name
            script.write_text("#!/bin/sh\nexit 0\n")
            script.chmod(0o700)
        self.env["PATH"] = str(mock) + os.pathsep + self.env["PATH"]

    def cli(self, *args):
        return subprocess.run([str(ROOT / "bin/omareel"), *args], env=self.env,
                              capture_output=True, text=True, timeout=20)

    def unchanged(self):
        self.assertEqual(self.victim.read_text(), "unrelated contents")

    def test_planted_config_and_lock_symlinks_are_rejected_without_truncation(self):
        for target in (self.config, Path(str(self.config) + ".lock")):
            with self.subTest(target=target):
                target.unlink(missing_ok=True)
                target.symlink_to(self.victim)
                result = self.cli("config", "merge", '{"mic":true}')
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(target.is_symlink())
                self.unchanged()
                target.unlink()
                self.config.write_text('{}')

    def test_predictable_old_tmp_symlink_is_never_used(self):
        Path(str(self.config) + ".tmp").symlink_to(self.victim)
        result = self.cli("config", "merge", '{"fps":60}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.config.read_text())["webcamPosition"], "top-right")
        self.assertEqual(json.loads(self.config.read_text())["fps"], 60)
        self.unchanged()

    def test_hardlinks_and_nonregular_entries_are_rejected(self):
        for target in (self.config, Path(str(self.config) + ".lock")):
            for kind in ("hardlink", "fifo", "directory"):
                with self.subTest(target=target, kind=kind):
                    target.unlink(missing_ok=True)
                    if kind == "hardlink": os.link(self.victim, target)
                    elif kind == "fifo": os.mkfifo(target)
                    else: target.mkdir()
                    self.assertNotEqual(self.cli("config", "get").returncode, 0)
                    self.unchanged()
                    if kind == "directory": target.rmdir()
                    else: target.unlink()
                    self.config.write_text('{}')

    def test_symlinked_parent_is_rejected(self):
        directory = self.root / "real"
        directory.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(directory, target_is_directory=True)
        self.env["OMAREEL_CONFIG"] = str(alias / "new.json")
        self.assertNotEqual(self.cli("config", "get").returncode, 0)
        self.assertEqual(list(directory.iterdir()), [])

    def test_shared_parent_and_writable_file_are_rejected(self):
        for target in (self.root, self.config):
            original = target.stat().st_mode & 0o777
            target.chmod(0o777)
            try:
                self.assertNotEqual(self.cli("config", "get").returncode, 0)
            finally:
                target.chmod(original)

    def test_new_nested_settings_are_private(self):
        self.env["OMAREEL_CONFIG"] = str(self.root / "new/nested/config.json")
        result = self.cli("config", "get")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(self.env["OMAREEL_CONFIG"]).stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / "new/nested").stat().st_mode & 0o777, 0o700)

    def test_invalid_objects_are_preserved_and_status_remains_available(self):
        for data in ("broken JSON", "[]", "null", '"text"'):
            self.config.write_text(data)
            self.assertNotEqual(self.cli("config", "get").returncode, 0)
            result = self.cli("status")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["phase"], "idle")
            self.assertEqual(self.config.read_text(), data)

    def test_failed_atomic_replace_keeps_previous_settings(self):
        original = self.config.read_bytes()
        with contextlib.closing(Settings(str(self.config))) as store:
            with patch("os.replace", side_effect=OSError("fixture failure")):
                with self.assertRaises(OSError):
                    store.update("merge", {"fps": 60})
        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(list(self.root.glob(".write-*")), [])

    def test_descriptor_stays_anchored_if_parent_path_is_swapped(self):
        directory = self.root / "private"
        directory.mkdir()
        path = directory / "settings.json"
        path.write_text('{}')
        with contextlib.closing(Settings(str(path))) as store:
            moved = self.root / "moved"
            directory.rename(moved)
            directory.symlink_to(self.root, target_is_directory=True)
            store.update("merge", {"fps": 60})
        self.assertEqual(json.loads((moved / "settings.json").read_text()), {"fps": 60})
        self.assertFalse((self.root / "settings.json").exists())

    def test_recursive_merge_preserves_false_arrays_and_legacy_placement(self):
        self.config.write_text('{"nested":{"keep":1,"enabled":true},"array":[1]}')
        result = self.cli("config", "merge", '{"nested":{"enabled":false},"array":[2],"webcamCorner":"top-left"}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.config.read_text()), {
            "nested": {"keep": 1, "enabled": False}, "array": [2], "webcamPosition": "top-left"})

    def test_managed_credentials_reject_planted_lock_and_config(self):
        conf = self.root / "rclone.conf"
        for target in (conf, Path(str(conf) + ".omareel.lock")):
            target.unlink(missing_ok=True)
            target.symlink_to(self.victim)
            with patch.dict(os.environ, OMAREEL_ACCESS_KEY_ID="fixture", OMAREEL_SECRET_ACCESS_KEY="fixture"):
                with self.assertRaises((OSError, ValueError)):
                    upload.save({"provider": "s3", "region": "us-east-1", "bucket": "fixture"}, conf)
            self.unchanged()
            target.unlink()

    def test_stop_and_toggle_save_locally_with_missing_invalid_or_linked_settings(self):
        raw = self.root / "take.raw.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=10:d=1",
                        "-c:v", "libx264", str(raw)], check=True, timeout=10)
        original = raw.read_bytes()
        self.assertEqual(self.cli("status").returncode, 0)
        statefile = self.root / "omareel/state.json"
        for command, damage in (("stop", "invalid"), ("toggle", "missing"), ("stop", "symlink")):
            with self.subTest(command=command, damage=damage):
                self.config.unlink(missing_ok=True)
                if damage == "invalid": self.config.write_text("broken JSON")
                elif damage == "symlink": self.config.symlink_to(self.victim)
                statefile.write_text(json.dumps({"phase":"recording", "file":str(raw),
                    "mic":False, "desktop":False, "denoise":True, "upload":"r2"}))
                result = self.cli(command)
                self.assertEqual(result.returncode, 0, result.stderr)
                state = json.loads(statefile.read_text())
                self.assertEqual(state["phase"], "done")
                self.assertEqual(state["url"], "")
                self.assertFalse(state["canUpload"])
                self.assertIn("Settings unavailable", state["warning"])
                self.assertTrue(Path(state["file"]).is_file())
                self.assertEqual(raw.read_bytes(), original)
                if damage == "invalid": self.assertEqual(self.config.read_text(), "broken JSON")
                elif damage == "missing": self.assertFalse(self.config.exists())
                else: self.assertTrue(self.config.is_symlink())
                self.unchanged()


if __name__ == "__main__":
    unittest.main(verbosity=2)
