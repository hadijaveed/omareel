#!/usr/bin/env python3
"""Runtime attack fixtures and normal startup/locking; no desktop/device access."""
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("runtime", ROOT / "bin/runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeSecurity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="omareel-runtime-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.directory = self.base / "omareel"
        self.config = self.base / "config.json"
        self.env = dict(os.environ, XDG_RUNTIME_DIR=str(self.base), OMAREEL_CONFIG=str(self.config))
        self.env.pop("OMAREEL_OPERATION_LOCKED", None)
        self.victim = self.base / "untouched"
        self.victim.write_text("unrelated contents")

    def cli(self, *args, env=None):
        return subprocess.run([str(ROOT / "bin/omareel"), *args], env=env or self.env,
                              capture_output=True, text=True, timeout=10)

    def helper(self, *args, data=None):
        return subprocess.run([sys.executable, str(ROOT / "bin/runtime.py"), *args],
                              env=self.env, input=data, capture_output=True, text=True, timeout=10)

    def store(self):
        result = runtime.Runtime(str(self.base))
        self.addCleanup(result.close)
        return result

    def assert_victim_untouched(self):
        self.assertEqual(self.victim.read_text(), "unrelated contents")
        self.assertEqual(self.victim.stat().st_nlink, 1)

    def test_fresh_start_creates_private_directory_and_complete_state(self):
        self.assertEqual(self.cli("status").returncode, 0)
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        for path in self.directory.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(json.loads((self.directory / "state.json").read_text())["phase"], "idle")

    def test_owned_legacy_directory_is_tightened_without_losing_state(self):
        self.directory.mkdir(mode=0o755)
        state = self.directory / "state.json"
        state.write_text('{"phase":"recording","id":"existing"}')
        self.assertEqual(self.cli("status").returncode, 0)
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        self.assertEqual(json.loads(state.read_text())["id"], "existing")

    def test_missing_relative_or_shared_tmp_runtime_is_rejected_before_config(self):
        for value in (None, "", "relative-path", "/tmp"):
            with self.subTest(value=value):
                env = dict(self.env)
                if value is None:
                    env.pop("XDG_RUNTIME_DIR", None)
                else:
                    env["XDG_RUNTIME_DIR"] = value
                result = self.cli("status", env=env)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.config.exists())
                self.assertFalse(self.directory.exists())

    def test_symlinked_runtime_directory_is_rejected(self):
        destination = self.base / "elsewhere"
        destination.mkdir()
        self.directory.symlink_to(destination, target_is_directory=True)
        self.assertNotEqual(self.cli("status").returncode, 0)
        self.assertEqual(list(destination.iterdir()), [])
        self.assertFalse(self.config.exists())

    def test_symlink_in_any_session_path_component_is_rejected(self):
        alias = self.base / "alias"
        alias.symlink_to(self.base, target_is_directory=True)
        child = self.base / "child"
        child.mkdir()
        for path in (alias, alias / "child"):
            with self.subTest(path=path):
                self.assertNotEqual(self.cli("status", env=dict(self.env, XDG_RUNTIME_DIR=str(path))).returncode, 0)
        self.assertFalse(self.directory.exists())

    def test_writable_by_others_directories_are_rejected_not_repaired(self):
        self.directory.mkdir(mode=0o700)
        for path in (self.base, self.directory):
            for mode in (0o777, 0o770):
                with self.subTest(path=path, mode=mode):
                    path.chmod(mode)
                    try:
                        self.assertNotEqual(self.cli("status").returncode, 0)
                        self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
                        self.assertFalse(self.config.exists())
                    finally:
                        path.chmod(0o700)

    def test_foreign_owned_directory_and_file_metadata_are_rejected(self):
        store = self.store()
        store.write("state.json", b'{}')
        for name, directory in ((self.directory, True), (self.directory / "state.json", False)):
            info = list(name.stat())
            info[4] = os.geteuid() + 1
            with self.assertRaises(ValueError):
                runtime.check_owner(os.stat_result(info), directory=directory)

    def test_planted_startup_symlinks_leave_the_target_and_config_untouched(self):
        self.directory.mkdir(mode=0o700)
        for name in runtime.KNOWN_FILES:
            with self.subTest(name=name):
                link = self.directory / name
                link.symlink_to(self.victim)
                self.assertNotEqual(self.cli("status").returncode, 0)
                self.assertTrue(link.is_symlink())
                self.assert_victim_untouched()
                self.assertFalse(self.config.exists())
                link.unlink()

    def test_broken_symlink_is_rejected_without_creating_its_target(self):
        self.directory.mkdir(mode=0o700)
        missing = self.base / "must-not-be-created"
        (self.directory / "state.json").symlink_to(missing)
        self.assertNotEqual(self.cli("status").returncode, 0)
        self.assertFalse(missing.exists())

    def test_planted_hardlinks_are_rejected(self):
        self.directory.mkdir(mode=0o700)
        for name in runtime.KNOWN_FILES:
            with self.subTest(name=name):
                entry = self.directory / name
                os.link(self.victim, entry)
                self.assertNotEqual(self.cli("status").returncode, 0)
                self.assertEqual(self.victim.read_text(), "unrelated contents")
                entry.unlink()

    def test_fifos_and_directories_fail_without_blocking(self):
        self.directory.mkdir(mode=0o700)
        for name in runtime.KNOWN_FILES:
            with self.subTest(name=name):
                entry = self.directory / name
                os.mkfifo(entry)
                self.assertNotEqual(self.cli("status").returncode, 0)
                entry.unlink()
                entry.mkdir()
                self.assertNotEqual(self.cli("status").returncode, 0)
                entry.rmdir()

    def test_read_write_and_append_reject_links_planted_after_initialization(self):
        self.assertEqual(self.cli("status").returncode, 0)
        for action in ("read", "write", "append"):
            with self.subTest(action=action):
                entry = self.directory / "omareel.log"
                entry.symlink_to(self.victim)
                self.assertNotEqual(self.helper(action, entry.name, data="replacement").returncode, 0)
                self.assert_victim_untouched()
                entry.unlink()

    def test_predictable_old_temp_symlink_is_never_used(self):
        self.assertEqual(self.cli("status").returncode, 0)
        (self.directory / "state.json.tmp").symlink_to(self.victim)
        result = self.helper("write", "state.json", data='{"phase":"done"}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_victim_untouched()
        self.assertEqual(json.loads((self.directory / "state.json").read_text())["phase"], "done")

    def test_invalid_json_never_replaces_previous_state(self):
        self.assertEqual(self.cli("status").returncode, 0)
        before = (self.directory / "state.json").read_bytes()
        for data in ("", "broken", "[]"):
            self.assertNotEqual(self.helper("write", "state.json", data=data).returncode, 0)
            self.assertEqual((self.directory / "state.json").read_bytes(), before)

    def test_atomic_write_failure_preserves_state_and_removes_temp(self):
        store = self.store()
        store.write("state.json", b'{"phase":"recording"}')
        with patch.object(runtime.os, "replace", side_effect=OSError("fixture disk failure")):
            with self.assertRaises(OSError):
                store.write("state.json", b'{"phase":"done"}')
        self.assertEqual(store.read("state.json"), b'{"phase":"recording"}')
        self.assertEqual(list(self.directory.glob(".write-*")), [])

    def test_readers_only_observe_complete_atomic_writes(self):
        store = self.store()
        store.write("state.json", b'{"n":-1}')
        stop = threading.Event()
        failures = []
        def reader():
            while not stop.is_set():
                try:
                    self.assertIsInstance(json.loads(store.read("state.json"))["n"], int)
                except Exception as error:
                    failures.append(error)
                    break
        thread = threading.Thread(target=reader)
        thread.start()
        try:
            for number in range(40):
                store.write("state.json", json.dumps({"n": number, "data": "x" * 100000}).encode())
        finally:
            stop.set()
            thread.join()
        self.assertEqual(failures, [])

    def test_parallel_first_start_preserves_valid_state(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.cli("status"), range(12)))
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["phase"], "idle")

    def test_file_names_cannot_escape_runtime(self):
        store = self.store()
        for name in ("", ".", "..", "../untouched", str(self.victim)):
            with self.assertRaises(ValueError):
                store.write(name, b"replacement")
        self.assert_victim_untouched()

    def test_operation_lock_is_released_while_background_child_still_runs(self):
        pidfile = self.base / "background.pid"
        code = ("import subprocess,sys; from pathlib import Path; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)'], "
                "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=False); "
                f"Path({str(pidfile)!r}).write_text(str(p.pid))")
        result = self.helper("locked", sys.executable, "-c", code)
        self.assertEqual(result.returncode, 0, result.stderr)
        pid = int(pidfile.read_text())
        try:
            os.kill(pid, 0)
            again = self.helper("locked", sys.executable, "-c", "pass")
            self.assertEqual(again.returncode, 0, again.stderr)
        finally:
            os.kill(pid, signal.SIGTERM)

    def test_camera_mask_remains_decodable_and_rejects_planted_target(self):
        command = 'source "$1"; bubble_mask_png 256 144 circle "$RUNTIME_DIR/selfview-mask.png"'
        result = subprocess.run(["bash", "-c", command, "_", str(ROOT / "bin/omareel")],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        mask = self.directory / "selfview-mask.png"
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "json", str(mask)],
                               capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(probe.stdout)["streams"][0], {"width": 256, "height": 144})
        mask.unlink()
        mask.symlink_to(self.victim)
        result = subprocess.run(["bash", "-c", command, "_", str(ROOT / "bin/omareel")],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assert_victim_untouched()

    def test_runtime_fd_stays_anchored_if_directory_path_is_replaced(self):
        store = self.store()
        moved = self.base / "original-runtime"
        self.directory.rename(moved)
        self.directory.symlink_to(self.base, target_is_directory=True)
        store.write("untouched", b"private contents")
        self.assertEqual((moved / "untouched").read_bytes(), b"private contents")
        self.assert_victim_untouched()


if __name__ == "__main__":
    unittest.main(verbosity=2)
