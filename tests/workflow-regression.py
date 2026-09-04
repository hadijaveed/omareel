#!/usr/bin/env python3
"""Isolated CLI regressions; synthetic video, mocked desktop and uploads."""
import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(os.environ.get("OMAREEL_TEST_SOURCE", Path(__file__).resolve().parents[1] / "bin/omareel"))


class WorkflowRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="omareel-workflow-test-")
        self.root = Path(self.tmp.name)
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({"outputDir": str(self.root), "mic": False,
                                          "webcamPosition": "top-right"}))
        rclone_conf = self.root / "rclone.conf"
        rclone_conf.write_text("[fixture]\ntype = s3\n")
        self.env = dict(os.environ, OMAREEL_CONFIG=str(self.config), XDG_RUNTIME_DIR=self.tmp.name,
                        RCLONE_CONFIG=str(rclone_conf))
        self.runtime = self.root / "omareel"
        self.runtime.mkdir()
        self.env.pop("OMAREEL_OPERATION_LOCKED", None)

    def tearDown(self):
        self.tmp.cleanup()

    def helper(self, command, *args, check=True):
        return subprocess.run(["bash", "-c", 'source "$1"; shift; omarchy-shell(){ :; }; notify(){ :; }; ' + command,
                               "_", str(SOURCE), *args], env=self.env, capture_output=True,
                              text=True, check=check, timeout=20)

    def cli(self, *args):
        return subprocess.run([str(SOURCE), *args], env=self.env, capture_output=True, text=True, timeout=20)

    def test_parallel_settings_preserve_all_values(self):
        def change(i):
            return self.cli("config", "merge", json.dumps({"test" + str(i): i})).returncode
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(change, range(20))), [0]*20)
        result = json.loads(self.config.read_text())
        for i in range(20):
            self.assertEqual(result["test" + str(i)], i)
        self.assertFalse(result["mic"])
        self.assertEqual(result["webcamPosition"], "top-right")

    def test_busy_operation_cannot_start_stop_or_discard(self):
        with (self.runtime / "operation.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for command in ("start", "stop", "cancel", "upload", "rename"):
                with self.subTest(command=command):
                    self.assertEqual(self.cli(command).returncode, 75)

    def test_sharing_does_not_overwrite_active_recording_state(self):
        state = {"phase": "recording", "file": "in-progress.raw.mp4"}
        (self.runtime / "state.json").write_text(json.dumps(state))
        for command in ("upload", "rename", "page", "finalize"):
            self.assertEqual(self.cli(command, "last").returncode, 75)
            self.assertEqual(json.loads((self.runtime / "state.json").read_text()), state)

    def test_stale_pid_is_not_a_recorder(self):
        (self.runtime / "gsr.pid").write_text(str(os.getpid()))
        self.assertNotEqual(self.helper("gsr_running", check=False).returncode, 0)

    def test_window_clip_and_screen_exclude_reserved_bar(self):
        self.env["TEST_MONITORS"] = json.dumps([{"name": "DP-1", "x": 0, "y": 0,
                "width": 3840, "height": 1600, "scale": 1.25, "transform": 0, "reserved": [0,26,0,0]}])
        mock = 'hyprctl(){ printf "%s" "$TEST_MONITORS"; }; '
        clipped = self.helper(mock + 'visible_monitor_region -116 33 1678 1240').stdout.strip()
        self.assertEqual(clipped, "1562x1240+0+33")
        screen = self.helper(mock + 'monitor_capture_region DP-1').stdout.strip()
        self.assertEqual(screen, "3072x1254+0+26")
        self.env["TEST_MONITORS"] = json.dumps([{"name": "rotated", "x": -1080, "y": 0,
                "width": 1920, "height": 1080, "scale": 1, "transform": 1, "reserved": [0,0,0,32]}])
        self.assertEqual(self.helper(mock + 'monitor_capture_region rotated').stdout.strip(), "1080x1888+-1080+0")

    def test_camera_crop_keeps_aspect_for_every_shape_and_zoom(self):
        for shape, ratio in (("frame",16/9),("classic",4/3),("circle",1),("portrait",8/9)):
            previous = None
            for zoom in ("full", "close", "tight"):
                w, h = map(int,self.helper('camera_crop_size 1280 720 "$1" "$2"',shape,zoom).stdout.split())
                self.assertLessEqual(w,1280)
                self.assertLessEqual(h,720)
                self.assertEqual(w % 2 + h % 2,0)
                self.assertLess(abs(w/h-ratio),0.01)
                if previous:
                    self.assertLess(w*h,previous)
                previous = w*h

    def video(self):
        path = self.root / "take.mp4"
        subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc2=size=64x48:rate=5:duration=1",
                        "-c:v","libx264","-pix_fmt","yuv420p",str(path)],check=True,capture_output=True,timeout=10)
        return path

    def test_upload_and_rename_keep_identity_and_saved_actions(self):
        video = self.video()
        raw = self.root / "take.raw.mp4"
        raw.write_bytes(video.read_bytes())
        self.config.write_text(json.dumps({"outputDir":self.tmp.name,"upload":{
            "provider":"existing","remote":"fixture:bucket","publicBase":"https://example.test","playerPage":True}}))
        self.env["UPLOAD_TEST_DIR"] = str(self.root / "uploaded")
        mock = '''rclone(){ case "$1" in copyto) mkdir -p "$UPLOAD_TEST_DIR"; cp "$2" "$UPLOAD_TEST_DIR/${3##*/}";; *) return 1;; esac; };
wl-copy(){ cat >/dev/null; }; sleep(){ :; };
append_index "$1" "" stable-id; cmd_upload "$1" '--title=Demo <&>' '''
        result = self.helper(mock,str(video))
        self.assertEqual(result.stdout.strip(),"https://example.test/stable-id.html")
        entry = json.loads((self.root / "index.jsonl").read_text().splitlines()[-1])
        self.assertEqual(entry["id"],"stable-id")
        self.assertTrue(Path(entry["file"]).exists())
        self.assertTrue(Path(entry["file"].replace(".mp4",".raw.mp4")).exists())
        self.assertEqual(json.loads((self.runtime / "state.json").read_text())["phase"],"done")
        html = (self.root / "uploaded/stable-id.html").read_text()
        self.assertIn("Demo &lt;&amp;&gt;",html)
        self.assertIn('width="64" height="48"',html)

    def test_upload_failure_keeps_local_file_and_retry(self):
        video = self.video()
        self.config.write_text(json.dumps({"outputDir":self.tmp.name,"upload":{
            "provider":"existing","remote":"fixture:bucket"}}))
        result = self.helper('rclone(){ return 7; }; sleep(){ :; }; cmd_upload "$1"', str(video), check=False)
        self.assertNotEqual(result.returncode,0)
        state = json.loads((self.runtime / "state.json").read_text())
        self.assertEqual(state["phase"],"done")
        self.assertTrue(state["canUpload"])
        self.assertTrue(video.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
