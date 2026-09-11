#!/usr/bin/env python3
"""Exercise the production settings Process/watcher in native Quickshell."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
enclosing = runpy.run_path(str(ROOT / "tests/runtime-native.py"))["enclosing"]
source = (ROOT / "BarWidget.qml").read_text()
reader = enclosing(source, "id: configFile", "Process")
watcher = enclosing(source, 'path: (Quickshell.env("OMAREEL_CONFIG")', "FileView")
with tempfile.TemporaryDirectory(prefix="omareel-settings-native-") as directory:
    work = Path(directory)
    (work / "Omareel.js").write_bytes((ROOT / "Omareel.js").read_bytes())
    config = work / "config.json"
    victim = work / "victim.json"
    victim.write_text('{"fps":999}')
    for unsafe in (False, True):
        config.unlink(missing_ok=True)
        if unsafe:
            config.symlink_to(victim)
        else:
            config.write_text('{"fps":30}')
        (work / "shell.qml").write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import "Omareel.js" as Omareel
ShellRoot {
  Item {
    id: root
    property string cli: __CLI__
    property string home: __HOME__
    property var config: ({fps: 0})
    property string message: ""
    property bool edited: false
    QtObject { id: remoteRefresh; function restart() {} }
    __READER__
    __WATCHER__
    Process { id: edit; command: [root.cli, "config", "merge", '{"fps":60}'] }
    Component.onCompleted: configFile.reload()
    Timer {
      interval: 30; running: true; repeat: true
      onTriggered: {
        if (__UNSAFE__) {
          if (root.config.fps === 999) { console.error("READ PLANTED CONFIG"); Qt.quit() }
          else if (root.message.length) { console.log("SETTINGS NATIVE PASS"); Qt.quit() }
        } else if (root.config.fps === 30 && !root.edited) {
          root.edited = true
          edit.running = true
        } else if (root.config.fps === 60) {
          console.log("SETTINGS NATIVE PASS"); Qt.quit()
        }
      }
    }
    Timer { interval: 8000; running: true; onTriggered: { console.error("SETTINGS TIMEOUT"); Qt.quit() } }
  }
}
'''.replace("__CLI__", json.dumps(str(ROOT / "bin/omareel")))
            .replace("__HOME__", json.dumps(str(work))).replace("__READER__", reader)
            .replace("__WATCHER__", watcher).replace("__UNSAFE__", str(unsafe).lower()))
        env = dict(os.environ, XDG_RUNTIME_DIR=str(work), OMAREEL_CONFIG=str(config),
                   QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_QPA_PLATFORMTHEME="",
                   QT_QUICK_CONTROLS_STYLE="Basic")
        result = subprocess.run(["quickshell", "-p", str(work), "--no-color"], env=env,
                                capture_output=True, text=True, timeout=12)
        output = result.stdout + result.stderr
        assert result.returncode == 0 and "SETTINGS NATIVE PASS" in output, output
        assert "READ PLANTED" not in output and "SETTINGS TIMEOUT" not in output, output
        assert victim.read_text() == '{"fps":999}'
        print("PASS: settings symlink rejected by UI" if unsafe else "PASS: UI loads settings and observes external atomic merges")
