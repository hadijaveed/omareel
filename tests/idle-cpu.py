#!/usr/bin/env python3
"""Manual idle measurement: shell + live/reaped descendants; no device access.

Run from the desktop session after plugin reload has settled. Status counts
are sampled observations, not an exhaustive exec trace. CPU includes other
shell plugins; this script reports evidence, not a machine-independent limit.
"""
import argparse, ctypes, json, os, struct, time
from pathlib import Path
parser=argparse.ArgumentParser(); parser.add_argument('--seconds',type=int,default=20); parser.add_argument('--pid',type=int,default=None); args=parser.parse_args()
if args.seconds < 1 or args.seconds > 60:
    parser.error('--seconds must be between 1 and 60')
if args.pid is None:
    shells=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit(): continue
        try:
            cmd=(path/'cmdline').read_bytes().split(b'\0')
            if (path.stat().st_uid == os.getuid()
                    and Path(os.readlink(path/'exe')).name in ('quickshell','qs')
                    and any(b'/omarchy/shell' in arg for arg in cmd)):
                shells.append(int(path.name))
        except OSError: pass
    if len(shells) != 1:
        parser.error('Pass --pid for the running Omarchy shell')
    args.pid=shells[0]
hz=os.sysconf('SC_CLK_TCK')
def snapshot():
    rows={}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit(): continue
        try:
            values=(path/'stat').read_text().rsplit(')',1)[1].split()
            rows[int(path.name)]=(int(values[1]),sum(int(values[i]) for i in (11,12,13,14)),int(values[19]))
        except (OSError,ValueError): pass
    descendants={args.pid}
    while True:
        more={pid for pid,row in rows.items() if row[0] in descendants}
        if more <= descendants: break
        descendants |= more
    return rows,descendants
libc=ctypes.CDLL(None,use_errno=True)
fd=libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
mask=0x2|0x4|0x8|0x40|0x80|0x100|0x200|0x400|0x800
if fd<0 or libc.inotify_add_watch(fd,os.fsencode(os.environ['XDG_RUNTIME_DIR']+'/omareel'),mask)<0: raise OSError(ctypes.get_errno())
rows,tree=snapshot(); start_ticks=sum(rows[p][1] for p in tree if p in rows); root_start=rows[args.pid][2]
started=time.monotonic(); seen=set(); events={}; peak=0
while time.monotonic()-started<args.seconds:
    rows,tree=snapshot(); peak=max(peak,len(tree)-1)
    for pid in tree-{args.pid}:
        try:
            cmd=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
            if b'status' in cmd and any(a.endswith(b'/bin/omareel') for a in cmd): seen.add((pid,rows[pid][2]))
        except OSError: pass
    try: data=os.read(fd,65536)
    except BlockingIOError: data=b''
    offset=0
    while offset<len(data):
        _,bits,_,length=struct.unpack_from('iIII',data,offset); offset+=16+length
        key=hex(bits); events[key]=events.get(key,0)+1
    time.sleep(.05)
rows,tree=snapshot(); elapsed=time.monotonic()-started
assert rows[args.pid][2]==root_start, 'Shell restarted during measurement'
end_ticks=sum(rows[p][1] for p in tree if p in rows)
print(json.dumps(dict(seconds=round(elapsed,2),shell_pid=args.pid,cpu_seconds_including_waited_and_live_children=round((end_ticks-start_ticks)/hz,3),percent_one_cpu=round(100*(end_ticks-start_ticks)/hz/elapsed,2),observed_status_processes=len(seen),peak_live_descendants=peak,directory_events=events),indent=2))
os.close(fd)
