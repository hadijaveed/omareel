#!/usr/bin/env python3
"""Bounded reads under a memory ceiling, growing files, pipes and log rotation."""
import concurrent.futures
import contextlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import runtime
from settings import Settings


def memory_ceiling():
    resource.setrlimit(resource.RLIMIT_AS, (64 * 1024 * 1024,) * 2)


class RuntimeLimits(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="omareel-limits-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.env = dict(os.environ, XDG_RUNTIME_DIR=str(self.root), OMAREEL_CONFIG=str(self.root / "config.json"))
        self.store = runtime.Runtime(str(self.root))
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.directory = self.root / "omareel"

    def command(self, *args, **kwargs):
        return subprocess.run([sys.executable, str(ROOT / "bin/runtime.py"), *args], env=self.env,
                              capture_output=True, timeout=10, preexec_fn=memory_ceiling, **kwargs)

    def sparse(self, name, size):
        path = self.directory / name
        with path.open("wb") as target:
            target.truncate(size)
        return path

    def test_sparse_gigabyte_files_rejected_without_buffering_under_64_mib(self):
        for name in ("state.json", "omareel.log", "selfview-mask.png", "gsr.pid"):
            with self.subTest(name=name):
                path = self.sparse(name, 8 * 1024**3)
                result = self.command("read", name)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(b"byte limit", result.stderr)
                self.assertNotIn(b"MemoryError", result.stderr)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(path.stat().st_size, 8 * 1024**3)

    def test_regular_stdin_rejected_before_buffering_and_preserves_state(self):
        original = self.store.read("state.json")
        with self.sparse("large-input", 8 * 1024**3).open("rb") as source:
            result = self.command("write", "state.json", stdin=source)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(b"byte limit", result.stderr)
        self.assertEqual(self.store.read("state.json"), original)
        self.assertEqual(list(self.directory.glob(".write-*")), [])

    def test_oversized_pipe_is_rejected_without_waiting_for_eof(self):
        original = self.store.read("state.json")
        process = subprocess.Popen([sys.executable, str(ROOT / "bin/runtime.py"), "write", "state.json"],
                                   env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, preexec_fn=memory_ceiling)
        try:
            process.stdin.write(b"x" * (runtime.MAX_JSON_BYTES + 1))
            process.stdin.flush()
            # Keep our writer open: the helper must stop at limit+1, not EOF.
            self.assertEqual(process.wait(timeout=5), 1)
            self.assertIn(b"byte limit", process.stderr.read())
        finally:
            if process.poll() is None: process.kill()
            process.communicate()
        self.assertEqual(self.store.read("state.json"), original)

    def test_metadata_check_precedes_any_read(self):
        with self.sparse("oversized", runtime.MAX_FILE_BYTES + 1).open("rb") as source:
            with patch.object(source, "read", side_effect=AssertionError("buffered oversized file")):
                with self.assertRaisesRegex(ValueError, "byte limit"):
                    runtime.read_limited(source, runtime.MAX_FILE_BYTES)

    def test_growth_after_stat_still_has_bounded_read_and_rejects_overflow(self):
        with self.sparse("growing", runtime.MAX_JSON_BYTES + 1).open("rb") as source:
            info = list(os.fstat(source.fileno()))
            info[6] = 0  # Simulate growth after the descriptor's size check.
            with patch.object(runtime.os, "fstat", return_value=os.stat_result(info)):
                with patch.object(source, "read", wraps=source.read) as read:
                    with self.assertRaisesRegex(ValueError, "byte limit"):
                        runtime.read_limited(source, runtime.MAX_JSON_BYTES)
                    read.assert_called_once_with(runtime.MAX_JSON_BYTES + 1)

    def test_binary_and_json_exact_boundaries_round_trip(self):
        for name in ("state.json", "selfview-mask.png", "gsr.pid"):
            limit = self.store.limit(name)
            data = b"x" * limit
            if name.endswith(".json"):
                data = b'{"data":"' + b"x" * (limit - 11) + b'"}'
            self.assertEqual(len(data), limit)
            result = self.command("write", name, input=data)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.store.read(name), data)
            result = self.command("write", name, input=data + b"x")
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(self.store.read(name), data)

    def test_in_memory_writes_reject_before_creating_a_temporary(self):
        with self.assertRaisesRegex(ValueError, "byte limit"):
            self.store.write("state.json", b"x" * (runtime.MAX_JSON_BYTES + 1))
        self.assertEqual(list(self.directory.glob(".write-*")), [])

    def test_oversized_settings_and_patch_do_not_replace_preferences(self):
        path = self.root / "config.json"
        path.write_text('{"mic":false}')
        original = path.read_bytes()
        for action in ("ensure", "merge"):
            with self.sparse("large-input", 8 * 1024**3).open("rb") as source:
                result = subprocess.run([sys.executable, str(ROOT / "bin/settings.py"), str(path), action],
                    stdin=source, capture_output=True, timeout=5, preexec_fn=memory_ceiling)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn(b"byte limit", result.stderr)
            self.assertEqual(path.read_bytes(), original)
        with path.open("wb") as target: target.truncate(8 * 1024**3)
        with contextlib.closing(Settings(str(path))) as settings:
            with self.assertRaisesRegex(ValueError, "byte limit"):
                settings.value()

    def test_settings_limit_applies_to_custom_names_and_merged_output(self):
        path = self.root / "custom-preferences"
        path.write_text(json.dumps({"a": "x" * (runtime.MAX_JSON_BYTES // 2)}))
        original = path.read_bytes()
        with contextlib.closing(Settings(str(path))) as settings:
            with self.assertRaisesRegex(ValueError, "byte limit"):
                settings.update("merge", {"b": "y" * (runtime.MAX_JSON_BYTES // 2)})
        self.assertEqual(path.read_bytes(), original)

    def test_auxiliary_settings_and_camera_inputs_are_also_bounded(self):
        large = self.sparse("large-input", 8 * 1024**3)
        commands = [
            [str(ROOT / "bin/system-check.py"), "check", str(large), "area"],
            [str(ROOT / "bin/system-check.py"), "camera"],
            [str(ROOT / "bin/upload-config.py"), "status", str(large), str(self.root / "rclone.conf")],
            ["-c", "import sys,importlib; sys.dont_write_bytecode=True; sys.path.insert(0,sys.argv[1]); "
             "importlib.import_module('upload-config').read_remotes(sys.argv[2])", str(ROOT / "bin"), str(large)],
        ]
        for command in commands:
            with self.subTest(command=command), large.open("rb") as source:
                result = subprocess.run([sys.executable, *command], stdin=source, capture_output=True,
                                        timeout=5, preexec_fn=memory_ceiling)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(b"byte limit", result.stderr)
                self.assertNotIn(b"MemoryError", result.stderr)

    def test_logs_rotate_without_interrupting_stream_and_keep_newest_output(self):
        old = self.sparse("omareel.log", 8 * 1024**3)
        # An old large log must not make Stop/status unavailable.
        self.assertEqual(self.command("init").returncode, 0)
        contents = b"x" * (runtime.MAX_LOG_BYTES * 2) + b"LATEST-PROGRESS\n"
        result = self.command("append", "omareel.log", input=contents)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLessEqual(old.stat().st_size, runtime.MAX_LOG_BYTES)
        self.assertTrue(self.store.read("omareel.log").endswith(b"LATEST-PROGRESS\n"))
        self.assertEqual(old.stat().st_mode & 0o777, 0o600)

    def test_parallel_log_producers_cannot_exceed_limit(self):
        source = self.root / "stream"
        source.write_bytes(b"x" * runtime.CHUNK_BYTES)
        def append(_):
            with source.open("rb") as stream:
                self.store.append_stream("omareel.log", stream.fileno())
        with patch.object(runtime, "MAX_LOG_BYTES", runtime.CHUNK_BYTES * 2):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(append, range(12)))
            self.assertLessEqual((self.directory / "omareel.log").stat().st_size, runtime.MAX_LOG_BYTES)

    def test_append_cannot_bypass_state_size_or_json_validation(self):
        original = self.store.read("state.json")
        result = self.command("append", "state.json", input=b"invalid")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.store.read("state.json"), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
