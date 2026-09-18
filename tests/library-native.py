#!/usr/bin/env python3
"""Production library reader/watchers reject oversized and redirected indexes."""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
enclosing = runpy.run_path(str(ROOT / "tests/runtime-native.py"))["enclosing"]
source = (ROOT / "BarWidget.qml").read_text()
reader = enclosing(source, "id: indexFile", "Process")
watcher = enclosing(source, "path: root.outputDir\n", "FileView")
for mode in ("large", "symlink"):
    with tempfile.TemporaryDirectory(prefix="omareel-library-native-") as directory:
        work = Path(directory)
        (work / "bin").symlink_to(ROOT / "bin", target_is_directory=True)
        shutil.copyfile(ROOT / "Omareel.js", work / "Omareel.js")
        library = work / "videos"
        library.mkdir()
        index = library / "index.jsonl"
        index.write_text(json.dumps(dict(file="example.mp4",title="example"))+"\n")
        victim = work / "victim"
        victim.write_text(json.dumps(dict(file="planted.mp4")))
        operation = "p.unlink(); p.symlink_to(sys.argv[2])" if mode == "symlink" else "t=p.with_suffix('.new'); f=t.open('wb'); f.truncate(8*1024**3); f.close(); t.replace(p)"
        command = ["python3", "-c", "import sys; from pathlib import Path; p=Path(sys.argv[1]); " + operation, str(index), str(victim)]
        qml = '''import QtQuick
import Quickshell
import Quickshell.Io
import "Omareel.js" as Omareel
ShellRoot {
  Item {
    id: root
    property string outputDir: __DIRECTORY__
    property var recordings: []
    property string selectedFile: ""
    property string message: ""
    property bool updated: false
    __READER__
    __WATCHER__
    Component.onCompleted: indexFile.reload()
    Process { id: update; command: __COMMAND__ }
    Timer { interval: 30; repeat: true; running: true; onTriggered: {
      if (!root.updated && root.recordings.length === 1) {
        if (root.recordings[0].file !== "example.mp4") console.error("UNSAFE LIBRARY")
        root.updated = true; update.running = true
      } else if (root.updated && root.message && root.recordings.length === 0) {
        console.log("LIBRARY NATIVE PASS"); Qt.quit()
      }
    } }
    Timer { interval: 8000; running: true; onTriggered: { console.error("TIMEOUT", JSON.stringify(root.recordings), root.message, root.updated); Qt.quit() } }
  }
}
'''.replace("__DIRECTORY__", json.dumps(str(library))).replace("__READER__", reader).replace("__WATCHER__", watcher).replace("__COMMAND__", json.dumps(command))
        (work / "shell.qml").write_text(qml)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", XDG_RUNTIME_DIR=str(work))
        result = subprocess.run(["quickshell","-p",str(work),"--no-color"],env=env,capture_output=True,text=True,timeout=12)
        logs = result.stdout + result.stderr
        assert result.returncode == 0 and "LIBRARY NATIVE PASS" in logs, logs
        assert not any(error in logs for error in ("UNSAFE LIBRARY", "ReferenceError", "TypeError", "Failed to load configuration")), logs
        assert json.loads(victim.read_text())["file"] == "planted.mp4"
        print("PASS: production library reader/watchers", mode)
