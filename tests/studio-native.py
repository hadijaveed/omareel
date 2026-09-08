#!/usr/bin/env python3
"""Optional Omarchy-only UI smoke: offscreen, real controls/CLI, synthetic media.

Run on an Omarchy desktop after the portable regression suite. This is not a
physical recording test. Never reloads the user's shell or accesses devices.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NATIVE = Path("/usr/share/omarchy/shell")


def main():
    if not shutil.which("quickshell") or not (NATIVE/"Ui").is_dir():
        raise SystemExit("Requires Omarchy native UI and Quickshell; run studio-regression.py on other hosts.")
    spec = importlib.util.spec_from_file_location("studio", ROOT/"bin/studio.py")
    studio = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(studio)
    with tempfile.TemporaryDirectory(prefix="omareel-studio-native-") as directory:
        temp = Path(directory)
        for name in ("StudioEditor.qml","PlainDropdown.qml","PlainToggle.qml"):
            shutil.copyfile(ROOT/name,temp/name)
        for name in ("Commons","Ui"):
            (temp/name).symlink_to(NATIVE/name,target_is_directory=True)
        video = temp/"test.mp4"
        subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc2=size=320x180:rate=10:duration=1.5",
                        "-c:v","libx264",str(video)],check=True,capture_output=True,timeout=20)
        config = temp/"config.json"
        config.write_text(json.dumps({"outputDir":directory,"mic":False,"studio":{"enabled":False},"upload":{"provider":"none"}}))
        # Native export calls these desktop hooks. Isolate them from the real
        # shell/clipboard; all media, settings, indexes and logs stay in temp.
        mocks = temp/"mockbin"
        mocks.mkdir()
        for name, body in (("omarchy-shell","exit 0"),("wl-copy","cat >/dev/null")):
            file = mocks/name
            file.write_text("#!/bin/sh\n"+body+"\n")
            file.chmod(0o700)
        screenshot = temp/"preview.png"
        template = (ROOT/"tests/studio-native.qml").read_text()
        for marker, value in {"__CLI__":str(ROOT/"bin/omareel"),"__VIDEO__":str(video),
                              "__DEFAULTS__":studio.DEFAULTS,"__SCREENSHOT__":str(screenshot)}.items():
            template = template.replace(marker,json.dumps(value))
        (temp/"shell.qml").write_text(template)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen",QT_QUICK_BACKEND="software",QT_QPA_PLATFORMTHEME="",XDG_RUNTIME_DIR=directory,
                   XDG_CACHE_HOME=str(temp/"cache"),OMAREEL_CONFIG=str(config),RCLONE_CONFIG=str(temp/"unused.conf"),
                   PATH=str(mocks)+os.pathsep+os.environ["PATH"])
        env.pop("OMAREEL_OPERATION_LOCKED",None)
        result = subprocess.run(["quickshell","-p",directory,"--no-color"],env=env,capture_output=True,text=True,timeout=60)
        output = result.stdout+result.stderr
        assert result.returncode == 0 and "STUDIO NATIVE PASS" in output, output
        for error in ("STUDIO TEST FAIL","ReferenceError","TypeError","Unable to assign","Failed to load configuration"):
            assert error not in output, output
        saved = json.loads(config.read_text())
        assert saved["studio"]["style"] == studio.DEFAULTS
        assert saved["studio"]["enabled"] is False and saved["mic"] is False
        state = json.loads((temp/"omareel/state.json").read_text())
        assert state["phase"] == "done" and state["file"] != str(video)
        assert Path(state["file"]).is_file() and video.is_file()
        assert screenshot.is_file()
        print("PASS: native offscreen Studio controls, real preview/export, preserved config and original")


if __name__ == "__main__":
    main()
