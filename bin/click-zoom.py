#!/usr/bin/env python3
"""Record ordinary left-click locations only for an opted-in active take.

Uses a temporary non-consuming Hyprland Lua binding. No keyboard hooks, device
permissions, persistent desktop configuration, or typed/window content.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
import uuid

DESCRIPTION = "Omareel recording click zoom"


def process_start(pid):
    return (Path("/proc")/str(pid)/"stat").read_text().rsplit(")",1)[1].split()[19]


def hypr(code):
    result = subprocess.run(["hyprctl", "repl", code], capture_output=True, text=True, timeout=3)
    if result.returncode or "OMAREEL_OK" not in result.stdout:
        raise ValueError("Zoom on clicks needs Hyprland's Lua API. Turn the toggle off to record normally.")


def check():
    hypr('assert(type(hl.bind)=="function" and type(hl.get_cursor_pos)=="function"); return "OMAREEL_OK"')
    binds = json.loads(subprocess.check_output(["hyprctl", "binds", "-j"], timeout=3))
    if any(b.get("key") == "mouse:272" and b.get("modmask") == 0
           and b.get("description") != DESCRIPTION for b in binds):
        raise ValueError("Another desktop binding uses plain left-click. Turn Zoom on clicks off to preserve that binding.")


def paths(raw):
    root = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "omareel"
    root.mkdir(parents=True, exist_ok=True)
    identity = Path(raw).name.removesuffix(".raw.mp4")
    if not re.fullmatch(r"[a-f0-9-]{36}", identity):
        raise ValueError("Invalid recording identity")
    return root / (identity + ".click-session.json"), root / (identity + ".click-events.jsonl")


def emit(session_path, token, x, y):
    path = Path(session_path)
    try:
        state = json.loads(path.read_text())
        if state["token"] != token or not state["active"]:
            return
        os.kill(state["pid"], 0)
        if process_start(state["pid"]) != state["pidStart"]:
            return
        rx, ry, rw, rh = state["region"]
        x, y = (x-rx)/rw, (y-ry)/rh
        at = time.time() - state["started"] - .1  # same startup trim as finalize_video
        if not 0 <= x <= 1 or not 0 <= y <= 1 or at < 0:
            return
        with open(state["events"], "a") as out:
            fcntl.flock(out, fcntl.LOCK_EX)
            if out.tell() < 1024*1024:
                out.write(json.dumps(dict(time=round(at,3),x=x,y=y))+"\n")
    except (OSError, ValueError, KeyError):
        return


def watch(raw, pid, region, started):
    session, events = paths(raw)
    match = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", region)
    if not match:
        raise ValueError("Zoom on clicks requires Area, Screen, or direct Window capture")
    w,h,x,y = map(int,match.groups())
    if w <= 0 or h <= 0:
        raise ValueError("Invalid recording region")
    check()
    token = uuid.uuid4().hex
    events.write_text("")
    events.chmod(0o600)
    state = dict(token=token,pid=pid,pidStart=process_start(pid),region=[x,y,w,h],started=started,events=str(events),active=True)
    session.write_text(json.dumps(state))
    session.chmod(0o600)
    command = shlex.join([sys.executable,str(Path(__file__).resolve()),"emit",str(session),token])
    # Never block the compositor: the callback only reads cursor coordinates
    # and launches a small helper asynchronously. set_enabled affects this
    # binding only; remove() on older Hyprland can remove unrelated bindings.
    code = f'''
      local state = _G.omareelClickZoom or {{}}
      state.token={json.dumps(token)}
      state.command={json.dumps(command)}
      _G.omareelClickZoom = state
      if not state.bind or state.bind:is_enabled()==nil then
        state.callback = function()
          local p=hl.get_cursor_pos()
          hl.exec_cmd(_G.omareelClickZoom.command .. string.format(" %.6f %.6f", p.x, p.y))
        end
        state.bind = hl.bind("mouse:272", state.callback,
          {{non_consuming=true, description={json.dumps(DESCRIPTION)}}})
      else state.bind:set_enabled(true) end
      assert(state.bind:is_enabled()); return "OMAREEL_OK"
    '''
    ready = session.with_suffix(".ready")
    try:
        hypr(code)
        ready.touch()
        while session.exists():
            try:
                os.kill(pid,0)
                if process_start(pid) != state["pidStart"]:
                    break
            except (ProcessLookupError,FileNotFoundError):
                break
            time.sleep(.2)
    finally:
        session.unlink(missing_ok=True)
        ready.unlink(missing_ok=True)
        try:
            hypr(f'if _G.omareelClickZoom and _G.omareelClickZoom.token=={json.dumps(token)} then '
                 '_G.omareelClickZoom.bind:set_enabled(false) end; return "OMAREEL_OK"')
        except (ValueError, subprocess.SubprocessError):
            pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("check","watch","emit","stop","collect"))
    parser.add_argument("args",nargs="*")
    args=parser.parse_args()
    if args.action=="check":
        check()
    elif args.action=="watch":
        watch(args.args[0],int(args.args[1]),args.args[2],float(args.args[3]))
    elif args.action=="emit":
        emit(args.args[0],args.args[1],float(args.args[2]),float(args.args[3]))
    else:
        session,events=paths(args.args[0])
        if args.action=="stop":
            session.unlink(missing_ok=True)
        else:
            clicks=[]
            if events.exists():
                for line in events.read_text().splitlines():
                    try: clicks.append(json.loads(line))
                    except ValueError: pass
            print(json.dumps(sorted(clicks,key=lambda e:e["time"])))


if __name__=="__main__":
    signal.signal(signal.SIGTERM,lambda *_:sys.exit(130))
    try: main()
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        print(str(error),file=sys.stderr)
        sys.exit(1)
