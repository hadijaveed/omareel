#!/usr/bin/env python3
"""Bounded desktop integration: callback delivery, cleanup, existing bindings.

No input is injected and no camera, microphone, or screen is recorded. A dummy
session observes clicks for less than a second in a temporary local directory.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
HELPER=ROOT/"bin/click-zoom.py"


def binds():
    values=json.loads(subprocess.check_output(["hyprctl","binds","-j"]))
    return [b for b in values if b.get("description")!="Omareel recording click zoom"]


def main():
    before=binds()
    with tempfile.TemporaryDirectory(prefix="omareel-click-native-") as work:
        env=dict(os.environ,XDG_RUNTIME_DIR=work)
        # Preserve compositor discovery while isolating helper session files.
        # hyprctl locates its actual socket via HYPRLAND_INSTANCE_SIGNATURE and
        # the runtime directory; wrap it to retain the desktop's real runtime.
        wrapper=Path(work)/"bin"
        wrapper.mkdir()
        import shutil,shlex
        real=shutil.which("hyprctl")
        binary=wrapper/"hyprctl"
        binary.write_text("#!/bin/sh\nexec env XDG_RUNTIME_DIR="+shlex.quote(os.environ["XDG_RUNTIME_DIR"])+" "+shlex.quote(real)+' "$@"\n')
        binary.chmod(0o700)
        env["PATH"]=str(wrapper)+os.pathsep+os.environ["PATH"]
        identity=str(uuid.uuid4())
        raw=Path(work)/(identity+".raw.mp4")
        proc=subprocess.Popen([sys.executable,str(HELPER),"watch",str(raw),str(os.getpid()),
                               "100000x100000+-50000+-50000",str(time.time()-.3)],env=env,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        session=Path(work)/"omareel"/(identity+".click-session.json")
        ready=session.with_suffix(".ready")
        events=Path(work)/"omareel"/(identity+".click-events.jsonl")
        try:
            deadline=time.monotonic()+4
            while not ready.exists() and time.monotonic()<deadline and proc.poll() is None:
                time.sleep(.02)
            assert ready.exists(), proc.communicate(timeout=1)
            result=subprocess.check_output(["hyprctl","repl",
                'assert(_G.omareelClickZoom.bind.non_consuming); _G.omareelClickZoom.callback(); return "OMAREEL_OK"'],text=True)
            assert "OMAREEL_OK" in result,result
            deadline=time.monotonic()+1
            while not events.stat().st_size and time.monotonic()<deadline:
                time.sleep(.02)
            assert events.stat().st_size,"Compositor callback did not produce a click"
            data=json.loads(events.read_text().splitlines()[0])
            assert set(data)=={"time","x","y"} and data["time"]>=0
            subprocess.run([sys.executable,str(HELPER),"stop",str(raw)],env=env,check=True)
            out,err=proc.communicate(timeout=3)
            assert proc.returncode==0,(out,err)
            check=subprocess.check_output(["hyprctl","repl",
                'assert(not _G.omareelClickZoom.bind:is_enabled()); return "OMAREEL_OK"'],text=True)
            assert "OMAREEL_OK" in check
            assert binds()==before,"An existing desktop binding changed"
        finally:
            session.unlink(missing_ok=True)
            if proc.poll() is None:
                proc.terminate();proc.communicate(timeout=3)
    print("PASS: compositor click callback, non-consuming binding, stop cleanup, existing bindings preserved")


if __name__=="__main__":main()
