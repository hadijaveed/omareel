#!/usr/bin/env python3
"""Synthetic media only: Studio geometry, encoding, safety and saved workflow."""
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("studio", ROOT / "bin/studio.py")
studio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(studio)
clickspec = importlib.util.spec_from_file_location("clickzoom",ROOT/"bin/click-zoom.py")
clickzoom = importlib.util.module_from_spec(clickspec)
clickspec.loader.exec_module(clickzoom)


class StudioRegression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="omareel-studio-test-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.env = dict(os.environ, XDG_RUNTIME_DIR=str(self.path), OMAREEL_CONFIG=str(self.path/"config.json"),
                        RCLONE_CONFIG=str(self.path/"unused-rclone.conf"))
        self.env.pop("OMAREEL_OPERATION_LOCKED", None)
        (self.path/"config.json").write_text(json.dumps({"outputDir":str(self.path), "upload":{"provider":"none"}}))
        self.video = self.path / "take ' & [%].mp4"
        self.ffmpeg("-f","lavfi","-i","testsrc2=size=320x180:rate=10:duration=1.5",
                    "-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=1.5",
                    "-c:v","libx264","-c:a","aac","-shortest",str(self.video))
        self.digest = hashlib.sha256(self.video.read_bytes()).digest()

    def ffmpeg(self, *args):
        return subprocess.run(["ffmpeg","-v","error","-nostdin",*args],check=True,capture_output=True,timeout=40)

    def render(self, action="export", opts=None, source=None, check=True):
        result = subprocess.run(["python3",str(ROOT/"bin/studio.py"),action,str(source or self.video),json.dumps(opts or {})],
                                env=self.env,capture_output=True,text=True,timeout=40)
        if check:
            self.assertEqual(result.returncode,0,result.stderr)
            return json.loads(result.stdout)
        return result

    def helper(self, script, *args, check=True):
        result = subprocess.run(["bash","-c",'source "$1"; shift; omarchy-shell(){ :; }; notify(){ :; }; '
                                 'wl-copy(){ cat >/dev/null; }; '+script,"_",str(ROOT/"bin/omareel"),*args],
                                env=self.env,capture_output=True,text=True,timeout=40)
        if check:
            self.assertEqual(result.returncode,0,result.stderr)
        return result

    def packets(self, path):
        data = subprocess.run(["ffprobe","-v","error","-select_streams","a","-show_packets",
                               "-show_data_hash","sha256","-show_entries","packet=data_hash,pts_time,duration_time",
                               "-of","json",str(path)],check=True,capture_output=True,text=True,timeout=10)
        return json.loads(data.stdout)["packets"]

    def test_all_geometry_combinations_stay_inside_canvas_without_stretch(self):
        for size, aspect, fit, zoom, frame, focus in itertools.product(
                ((1920,1080),(3840,1600),(1080,1920)), studio.CHOICES["aspect"],
                studio.CHOICES["fit"],studio.CHOICES["zoom"],studio.CHOICES["frame"],studio.CHOICES["focus"]):
            opts=studio.options(dict(aspect=aspect,fit=fit,zoom=zoom,frame=frame,focus=focus))
            g=studio.geometry(dict(width=size[0],height=size[1]),opts)
            self.assertLessEqual(max(g["w"],g["h"]),3840)
            for key in ("w","h","vw","vh","cw","ch"):
                self.assertEqual(g[key]%2,0)
                self.assertGreater(g[key],0)
            self.assertGreaterEqual(g["x"],0)
            self.assertGreaterEqual(g["y"]-g["bar"],0)
            self.assertLessEqual(g["x"]+g["vw"],g["w"])
            self.assertLessEqual(g["y"]+g["vh"],g["h"])
            self.assertLessEqual(g["cx"]+g["cw"],size[0])
            self.assertLessEqual(g["cy"]+g["ch"],size[1])
            self.assertLess(abs(g["vw"]/g["vh"]-g["cw"]/g["ch"]),.015)

    def test_each_preset_encodes_motion_and_copies_audio_packets_exactly(self):
        for preset in studio.PRESETS:
            with self.subTest(preset=preset):
                result=self.render(opts=dict(preset=preset))
                output=Path(result["file"])
                self.assertNotEqual(output,self.video)
                self.assertEqual(self.packets(output),self.packets(self.video))
                frames=self.ffmpeg("-i",str(output),"-map","0:v","-f","framemd5","-").stdout.decode()
                hashes=[line.split(",")[-1].strip() for line in frames.splitlines() if not line.startswith("#")]
                self.assertEqual(len(hashes),15)
                self.assertGreater(len(set(hashes)),10,"Styled recording must not freeze on the first frame")
                self.assertAlmostEqual(studio.probe(output)["duration"],1.5,delta=.1)
                self.assertEqual(hashlib.sha256(self.video.read_bytes()).digest(),self.digest)

    def test_preview_matches_first_export_frame(self):
        opts=dict(preset="paper",aspect="square",fit="fill",zoom="1.25",focus="top-right")
        preview=Path(self.render("preview",opts)["file"])
        output=Path(self.render(opts=opts)["file"])
        # Lossy H.264 introduces small differences; compare at preview resolution.
        a=self.ffmpeg("-i",str(preview),"-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","-").stdout
        b=self.ffmpeg("-i",str(output),"-vf","scale=960:640:force_original_aspect_ratio=decrease",
                      "-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","-").stdout
        self.assertEqual(len(a),len(b))
        self.assertLess(sum(abs(x-y) for x,y in zip(a,b))/len(a),4)

    def test_silent_recording_and_local_image(self):
        silent=self.path/"silent.mp4"
        self.ffmpeg("-i",str(self.video),"-an","-c:v","copy",str(silent))
        bg=self.path/"background [%] ' &.png"
        studio.png(bg,64,64,[bytes((32,64,96))*64]*64,2)
        result=self.render(opts=dict(background="image",image=str(bg),aspect="portrait"),source=silent)
        self.assertEqual(self.packets(result["file"]),[])
        self.assertLess(result["width"],result["height"])

    def test_timed_click_zoom_changes_only_its_range_and_preview_matches(self):
        still = self.path / "static.mp4"
        self.ffmpeg("-f","lavfi","-i","testsrc=size=640x360:rate=10:duration=4",
                    "-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=4",
                    "-vf","setpts=PTS-STARTPTS","-c:v","libx264","-pix_fmt","yuv420p",
                    "-c:a","aac","-shortest",str(still))
        event = dict(start=.5,end=2.5,amount=2,x=.85,y=.2)
        opts = dict(zooms=[event],previewTime=1.5)
        output = Path(self.render(opts=opts, source=still)["file"])
        plain = Path(self.render(source=still)["file"])
        self.assertEqual(self.packets(output),self.packets(still))
        self.assertAlmostEqual(studio.probe(output)["duration"],4,delta=.1)
        def frame(path, at, preview_size=False):
            args = ["-ss",str(at),"-i",str(path)]
            if preview_size:
                args += ["-vf","scale=960:640:force_original_aspect_ratio=decrease"]
            return self.ffmpeg(*args,"-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","-").stdout
        def difference(a,b):
            self.assertEqual(len(a),len(b))
            return sum(abs(x-y) for x,y in zip(a,b))/len(a)
        for at in (0,3):
            self.assertLess(difference(frame(output,at),frame(plain,at)),3)
        self.assertGreater(difference(frame(output,1.5),frame(plain,1.5)),15)
        preview = Path(self.render("preview",opts,source=still)["file"])
        self.assertLess(difference(frame(preview,0),frame(output,1.5,True)),4)
        # Fixed backdrop: sampled pixels outside the recording must stay stable.
        g = studio.geometry(studio.probe(still),studio.options(opts))
        a,b = frame(output,0),frame(output,1.5)
        edge = g["w"] * 3 * max(1,(g["y"]-g["bar"])//3)
        self.assertLess(difference(a[:edge],b[:edge]),1)

    def test_invalid_timed_zooms_are_rejected(self):
        event = dict(start=.2,end=1.2,amount=1.5,x=.5,y=.5)
        for events in ([event,event], [event | {"end":2}], [event | {"x":-1}],
                       [event | {"start":float("nan")}], [event | {"amount":10}],
                       [event | {"end":.3}], [{"start":0}]):
            self.assertNotEqual(self.render(opts=dict(zooms=events),check=False).returncode,0)
        self.assertEqual(hashlib.sha256(self.video.read_bytes()).digest(),self.digest)

    def test_recorded_clicks_zoom_screen_while_camera_stays_visible(self):
        raw = self.path / "layers.raw.mp4"
        raw.write_bytes(self.video.read_bytes())
        cam = self.path / "layers.cam.mp4"
        self.ffmpeg("-f","lavfi","-i","color=red:size=160x120:rate=10:duration=1.5",
                    "-c:v","libx264",str(cam))
        (self.path/"layers.cam.start").write_text("-0.1")
        audio = self.packets(self.video)
        metadata = studio.prepare_camera(raw,self.video,dict(size="medium",shape="portrait",position="top-right",zoom="full"))
        self.assertEqual(self.packets(self.video),audio)
        metadata |= dict(zoomOnClicks=True,clicks=[dict(time=.2,x=.2,y=.7)])
        (self.path/"index.jsonl").write_text(json.dumps(dict(file=str(self.video),capture=metadata))+"\n")
        result = self.render()
        self.assertTrue(result["clickZoom"])
        self.assertEqual(self.packets(result["file"]),audio)
        opts=studio.options({})
        geo=studio.geometry(studio.probe(self.video),opts)
        _,_,_,cx,cy=studio.camera_filter(metadata["camera"],geo["vw"],geo["vh"],self.path,4,5)
        bw=studio.even(studio.even(geo["vh"]*.22)*8/9)
        bh=studio.even(geo["vh"]*.22)
        for at in (0,.8,1.3):
            frame=self.ffmpeg("-ss",str(at),"-i",result["file"],"-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","-").stdout
            pixel=((geo["y"]+cy+bh//2)*geo["w"]+geo["x"]+cx+bw//2)*3
            red,green,blue=frame[pixel:pixel+3]
            self.assertGreater(red,180,"Camera must stay visible in its corner during the zoom")
            self.assertLess(max(green,blue),80)
        # Clean screen contains no baked-in webcam, so zoom cannot duplicate it.
        self.assertEqual(Path(metadata["screen"]).read_bytes(),raw.read_bytes())
        preview=self.render("preview")
        self.assertTrue(Path(preview["file"]).is_file())

    def test_click_zoom_ignores_rapid_repeats_and_outside_points(self):
        clicks=[dict(time=.2,x=.25,y=.75),dict(time=.3,x=.5,y=.5),dict(time=3,x=2,y=.5),dict(time=4,x=.8,y=.1)]
        events=studio.click_zooms(clicks,6)
        self.assertEqual(len(events),2)
        self.assertEqual(events[0],dict(start=.2,end=2.2,amount=1.5,x=.25,y=.75))
        self.assertEqual(events[1]["start"],4)

    def test_click_capture_records_only_active_in_region_points(self):
        session=self.path/"click-session.json"
        events=self.path/"events.jsonl"
        state=dict(token="test-token",active=True,pid=os.getpid(),pidStart=clickzoom.process_start(os.getpid()),
                   started=100,region=[-100,50,200,100],events=str(events))
        session.write_text(json.dumps(state))
        with patch.object(clickzoom.time,"time",return_value=100.6):
            clickzoom.emit(str(session),"test-token",-50,100)
            clickzoom.emit(str(session),"test-token",150,100) # outside recorded area
            clickzoom.emit(str(session),"other-token",-50,100)
            session.write_text(json.dumps(state | dict(pidStart="reused-pid")))
            clickzoom.emit(str(session),"test-token",-50,100)
            session.write_text(json.dumps(state | dict(active=False)))
            clickzoom.emit(str(session),"test-token",-50,100)
            session.unlink()
            clickzoom.emit(str(session),"test-token",-50,100)
        data=[json.loads(line) for line in events.read_text().splitlines()]
        self.assertEqual(data,[dict(time=.5,x=.25,y=.5)])

    def test_corners_are_antialiased_and_shadow_fades_inside_canvas(self):
        opts = studio.options({})
        geo = studio.geometry(dict(width=640,height=360),opts)
        _,decor,mask = studio.assets(self.path,geo,opts)
        alpha = self.ffmpeg("-i",str(decor),"-vf","alphaextract","-frames:v","1",
                            "-pix_fmt","gray","-f","rawvideo","-").stdout
        w,h = geo["w"],geo["h"]
        self.assertLessEqual(max(alpha[:w]+alpha[-w:]+alpha[::w]+alpha[w-1::w]),1)
        fade = [alpha[y*w+w//2] for y in range(geo["y"]+geo["vh"],h)]
        self.assertGreater(len(set(fade)),5)
        self.assertEqual(fade,sorted(fade,reverse=True))
        pixels = self.ffmpeg("-i",str(mask),"-frames:v","1","-pix_fmt","gray","-f","rawvideo","-").stdout
        self.assertTrue(any(0<p<255 for p in pixels),"Rounded edges need partial alpha coverage")

    def test_bad_image_options_or_source_never_replaces_original(self):
        bad=self.path/"not-an-image.png"
        bad.write_text('<svg><image href="http://127.0.0.1/private"/></svg>')
        for opts in ({"background":"image","image":"https://example.test/a.png"},
                     {"background":"image","image":str(bad)}, {"zoom":"1;movie=http://example.test"},
                     {"color":"red"}, {"shadow":"false"}, {"bogus":True}):
            self.assertNotEqual(self.render(opts=opts,check=False).returncode,0)
        self.assertNotEqual(self.render(source=bad,check=False).returncode,0)
        self.assertEqual(list(self.path.glob(".omareel-studio-*")),[])
        self.assertEqual(list(self.path.glob("*.mp4")),[self.video])
        self.assertEqual(hashlib.sha256(self.video.read_bytes()).digest(),self.digest)

    def test_export_is_distinct_and_saved_actions_select_correct_variant(self):
        self.helper('append_index "$1" "https://example.test/original.html" original-id Original',str(self.video))
        first=json.loads(self.helper('cmd_studio export "$1"',str(self.video)).stdout)["file"]
        second=json.loads(self.helper('cmd_studio export "$1"',first).stdout)["file"]
        self.assertNotEqual(first,second)
        entries=[json.loads(s) for s in (self.path/"index.jsonl").read_text().splitlines()]
        self.assertEqual(len({e["id"] for e in entries}),3)
        self.assertEqual(entries[0]["url"],"https://example.test/original.html")
        self.assertEqual(entries[1]["url"],"")
        self.assertEqual(entries[2]["studio"]["original"],str(self.video))
        state=json.loads((self.path/"omareel/state.json").read_text())
        self.assertEqual(state["file"],second)
        self.assertFalse(state["studioEnabled"])
        self.helper('cmd_studio select "$1"',str(self.video))
        state=json.loads((self.path/"omareel/state.json").read_text())
        self.assertEqual(state["url"],"https://example.test/original.html")
        self.assertEqual(state["file"],str(self.video))

    def test_renaming_original_updates_studio_source_reference(self):
        self.helper('append_index "$1" "" original-id Original; cmd_studio export "$1"',str(self.video))
        renamed=self.helper('rename_recording "$1" "A renamed take"',str(self.video)).stdout.strip()
        entries=[json.loads(s) for s in (self.path/"index.jsonl").read_text().splitlines()]
        self.assertEqual(entries[1]["studio"]["original"],renamed)
        self.assertTrue(Path(renamed).exists())

    def test_failed_export_does_not_change_saved_state(self):
        self.helper('set_state done file="$1" url="https://example.test/shared"',str(self.video))
        state=(self.path/"omareel/state.json").read_bytes()
        self.helper('cmd_studio export "$1" \'{"background":"image","image":"/missing/image.png"}\'',str(self.video),check=False)
        self.assertEqual((self.path/"omareel/state.json").read_bytes(),state)
        self.assertFalse((self.path/"index.jsonl").exists())

    def test_missing_original_cannot_silently_reframe_an_export(self):
        result=self.helper('append_index "$1" "" original-id; cmd_studio export "$1"',str(self.video))
        exported=json.loads(result.stdout)["file"]
        self.video.rename(self.path/"moved-original.mp4")
        failed=self.helper('cmd_studio export "$1"',exported,check=False)
        self.assertNotEqual(failed.returncode,0)
        self.assertIn("original is missing",failed.stderr)
        self.assertTrue(Path(exported).is_file())
        self.assertEqual(len((self.path/"index.jsonl").read_text().splitlines()),2)

    def test_studio_does_not_hide_an_existing_cleanup_warning(self):
        self.helper('set_state done file="$1" warning="Cleanup failed; original audio retained"; cmd_studio export "$1"',str(self.video))
        state=json.loads((self.path/"omareel/state.json").read_text())
        self.assertEqual(state["warning"],"Cleanup failed; original audio retained")

    def test_studio_commands_refuse_to_interrupt_recording(self):
        self.helper('set_state recording file="$1"',str(self.video))
        for action in ("preview","export","select"):
            result=subprocess.run([str(ROOT/"bin/omareel"),"studio",action,str(self.video)],env=self.env,capture_output=True)
            self.assertEqual(result.returncode,75)
        self.assertEqual(hashlib.sha256(self.video.read_bytes()).digest(),self.digest)

    def test_default_off_and_start_snapshot_preserved(self):
        defaults=json.loads(self.helper("default_config").stdout)
        self.assertFalse(defaults["studio"]["enabled"])
        self.helper('set_state recording studioEnabled=true; set_state processing; set_state done file="$1"',str(self.video))
        self.assertTrue(json.loads((self.path/"omareel/state.json").read_text())["studioEnabled"])
        # Test the actual settings snapshot prelude, before any device work.
        source=(ROOT/"bin/omareel").read_text()
        prelude=source.split("cmd_start() {",1)[1].split("  local arg",1)[0]
        for enabled, expected in ((False,"rclone false"),(True,"none true")):
            (self.path/"config.json").write_text(json.dumps({"studio":{"enabled":enabled},"upload":{"auto":True}}))
            script='upload_ready(){ return 0; }; snapshot(){ '+prelude+'printf "%s %s" "$upload" "$studio_enabled"; }; snapshot'
            self.assertEqual(self.helper(script).stdout,expected)

    def test_preview_cache_is_bounded_and_does_not_remove_unrelated_files(self):
        runtime=self.path/"omareel"
        runtime.mkdir()
        for i in range(12):
            (runtime/f"studio-preview-{i:032x}.png").write_bytes(b"old preview")
        unrelated=runtime/"studio-preview-personal.png"
        unrelated.write_bytes(b"keep")
        self.render("preview")
        self.assertEqual(len(list(runtime.glob("studio-preview-*.png"))),9)
        self.assertEqual(unrelated.read_bytes(),b"keep")

    def test_cancellation_reaps_child_and_keeps_original(self):
        # The same run wrapper owns FFmpeg. Check SIGTERM propagation/reaping
        # without a long encode or access to any real recording or device.
        pidfile=self.path/"child.pid"
        code='import importlib.util,signal,sys; s=importlib.util.spec_from_file_location("s",sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); signal.signal(signal.SIGTERM,lambda *_:sys.exit(130)); m.run([sys.executable,"-c","import os,time,pathlib; pathlib.Path("+repr(sys.argv[2])+").write_text(str(os.getpid())); time.sleep(30)"])'
        child=subprocess.Popen(["python3","-c",code,str(ROOT/"bin/studio.py"),str(pidfile)],stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                if pidfile.exists(): break
                time.sleep(.02)
            self.assertTrue(pidfile.exists())
            nested=int(pidfile.read_text())
            child.send_signal(signal.SIGTERM)
            child.communicate(timeout=5)
            self.assertEqual(child.returncode,130)
            with self.assertRaises(ProcessLookupError): os.kill(nested,0)
        finally:
            if child.poll() is None: child.kill(); child.communicate()
        self.assertEqual(hashlib.sha256(self.video.read_bytes()).digest(),self.digest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
