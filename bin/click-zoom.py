#!/usr/bin/env python3
"""Record ordinary left-click locations only for an opted-in active take.

Uses a temporary non-consuming Hyprland Lua binding. No keyboard hooks, device
permissions, persistent desktop configuration, or typed/window content.
"""
import argparse
import contextlib
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime import Runtime
from studio import run

DESCRIPTION = "Omareel recording click zoom"


def process_start(pid):
    return (Path("/proc")/str(pid)/"stat").read_text().rsplit(")",1)[1].split()[19]


def hypr(code):
    result = run(["hyprctl", "repl", code], 3).decode(errors="replace")
    if "OMAREEL_OK" not in result:
        raise ValueError("Zoom on clicks needs Hyprland's Lua API. Turn the toggle off to record normally.")


def check():
    hypr('assert(type(hl.bind)=="function" and type(hl.get_cursor_pos)=="function"); return "OMAREEL_OK"')
    binds = json.loads(run(["hyprctl", "binds", "-j"], 3))
    if any(b.get("key") == "mouse:272" and b.get("modmask") == 0
           and b.get("description") != DESCRIPTION for b in binds):
        raise ValueError("Another desktop binding uses plain left-click. Turn Zoom on clicks off to preserve that binding.")


def paths(raw):
    with contextlib.closing(Runtime()) as storage:
        storage.initialize()
        root = Path(storage.base) / "omareel"
    identity = Path(raw).name.removesuffix(".raw.mp4")
    if not re.fullmatch(r"[a-f0-9-]{36}", identity):
        raise ValueError("Invalid recording identity")
    return root / (identity + ".click-session.json"), root / (identity + ".click-events.jsonl")


def emit(session_path, token, x, y):
    path = Path(session_path)
    try:
        with contextlib.closing(Runtime()) as storage:
            if path.parent != Path(storage.base) / "omareel" or not re.fullmatch(r"[a-f0-9-]{36}\.click-session\.json", path.name):
                return
            state = json.loads(storage.read(path.name))
            if state["token"] != token or not state["active"]:
                return
            os.kill(state["pid"], 0)
            if process_start(state["pid"]) != state["pidStart"]:
                return
            rx, ry, rw, rh = state["region"]
            x, y = (x-rx)/rw, (y-ry)/rh
            at = time.time() - state["started"] - .1
            if not 0 <= x <= 1 or not 0 <= y <= 1 or at < 0:
                return
            events = path.with_name(path.name.replace(".click-session.json", ".click-events.jsonl"))
            if state["events"] != str(events):
                return
            with os.fdopen(storage.open(events.name, os.O_WRONLY | os.O_APPEND, create=True), "a") as out:
                fcntl.flock(out, fcntl.LOCK_EX)
                if os.fstat(out.fileno()).st_size < 1024*1024:
                    out.write(json.dumps(dict(time=round(at,3),x=x,y=y))+"\n")
    except (OSError, ValueError, KeyError):
        return


def watch(raw, pid, region, started):
    with contextlib.closing(Runtime()) as storage:
        session, events = paths(raw)
        match = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", region)
        if not match:
            raise ValueError("Zoom on clicks requires Area, Screen, or direct Window capture")
        w,h,x,y = map(int,match.groups())
        if w <= 0 or h <= 0:
            raise ValueError("Invalid recording region")
        check()
        token = uuid.uuid4().hex
        storage.write(events.name, b"")
        state = dict(token=token,pid=pid,pidStart=process_start(pid),region=[x,y,w,h],started=started,events=str(events),active=True)
        storage.write(session.name, json.dumps(state).encode())
        command = shlex.join(["env", "XDG_RUNTIME_DIR=" + storage.base, sys.executable,str(Path(__file__).resolve()),"emit",str(session),token])
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
            storage.write(ready.name, b"")
            while session.exists():
                try:
                    os.kill(pid,0)
                    if process_start(pid) != state["pidStart"]:
                        break
                except (ProcessLookupError,FileNotFoundError):
                    break
                time.sleep(.2)
        finally:
            for path in (session, ready):
                try:
                    if storage.inspect(path.name):
                        os.unlink(path.name, dir_fd=storage.fd)
                except (OSError, ValueError):
                    pass  # Preserve unsafe entries, but always disable the binding below.
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
        with contextlib.closing(Runtime()) as storage:
            if args.action=="stop":
                if storage.inspect(session.name):
                    os.unlink(session.name, dir_fd=storage.fd)
            else:
                clicks=[]
                if storage.inspect(events.name):
                    for line in storage.read(events.name).decode().splitlines():
                        try: clicks.append(json.loads(line))
                        except ValueError: pass
                print(json.dumps(sorted(clicks,key=lambda e:e["time"])))


if __name__=="__main__":
    signal.signal(signal.SIGTERM,lambda *_:sys.exit(130))
    try: main()
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        print(str(error),file=sys.stderr)
        sys.exit(1)
