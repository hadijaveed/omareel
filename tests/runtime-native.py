#!/usr/bin/env python3
"""Actual startup Process and state watchers in native Quickshell, isolated."""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
block = runpy.run_path(str(ROOT / "tests/text-security.py"))["block"]


def enclosing(source, marker, kind):
    start = source.rfind(kind + " {", 0, source.index(marker))
    return kind + " {" + block(source[start:], kind + " {") + "}"


def main():
    assert shutil.which("quickshell"), "Requires native Quickshell"
    with tempfile.TemporaryDirectory(prefix="omareel-runtime-native-") as directory:
        for filename in ("BarWidget.qml", "Panel.qml"):
            source = (ROOT / filename).read_text()
            for unsafe in (False, True):
                work = Path(directory) / (filename + ("-unsafe" if unsafe else "-normal"))
                work.mkdir(mode=0o700)
                runtime = work / "omareel"
                victim = work / "victim.json"
                victim.write_text('{"phase":"done","id":"planted"}')
                if unsafe:
                    runtime.mkdir(mode=0o700)
                    (runtime / "state.json").symlink_to(victim)
                shutil.copyfile(ROOT / "Omareel.js", work / "Omareel.js")
                startup = enclosing(source, 'command: [root.cli, "status"]', "Process")
                state = enclosing(source, "id: stateFile", "FileView")
                watcher = enclosing(source, 'path: root.runtimeReady ? root.runtimeDir : ""', "FileView")
                command = ["bash", "-c", 'source "$1"; omarchy-shell(){ :; }; set_state done id=native-test',
                           "_", str(ROOT / "bin/omareel")]
                (work / "shell.qml").write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import "Omareel.js" as Omareel
ShellRoot {
  Item {
    id: root
    property string cli: __CLI__
    property string runtimeDir: __RUNTIME__
    property bool runtimeReady: false
    property var state: ({phase: "idle"})
    property string message: ""
    property bool readPlanted: false
    property bool startedWrite: false
    onStateChanged: { if (state.id === "planted") readPlanted = true }
    QtObject { id: configFile; function reload() {} }
    __STATE__
    __WATCHER__
    __STARTUP__
    Process { id: update; command: __COMMAND__ }
    Timer {
      interval: 30; running: true; repeat: true
      onTriggered: {
        if (__UNSAFE__) {
          if (root.state.phase === "error") {
            if (root.runtimeReady || root.readPlanted) console.error("UNSAFE RUNTIME READ")
            else console.log("RUNTIME NATIVE PASS")
            Qt.quit()
          }
        } else if (root.runtimeReady && !root.startedWrite) {
          root.startedWrite = true
          update.running = true
        } else if (root.state.id === "native-test") {
          console.log("RUNTIME NATIVE PASS")
          Qt.quit()
        }
      }
    }
    Timer { interval: 8000; running: true; onTriggered: { console.error("RUNTIME NATIVE TIMEOUT"); Qt.quit() } }
  }
}
'''.replace("__CLI__", json.dumps(str(ROOT / "bin/omareel")))
                    .replace("__RUNTIME__", json.dumps(str(runtime))).replace("__STATE__", state)
                    .replace("__WATCHER__", watcher).replace("__STARTUP__", startup)
                    .replace("__COMMAND__", json.dumps(command)).replace("__UNSAFE__", str(unsafe).lower()))
                env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                           QT_QUICK_CONTROLS_STYLE="Basic", QT_QPA_PLATFORMTHEME="", XDG_RUNTIME_DIR=str(work),
                           XDG_CACHE_HOME=str(work / "cache"), OMAREEL_CONFIG=str(work / "config.json"))
                result = subprocess.run(["quickshell", "-p", str(work), "--no-color"],
                                        env=env, capture_output=True, text=True, timeout=12)
                logs = result.stdout + result.stderr
                assert result.returncode == 0 and "RUNTIME NATIVE PASS" in logs, logs
                for error in ("ReferenceError", "TypeError", "Failed to load configuration", "UNSAFE RUNTIME READ"):
                    assert error not in logs, logs
                assert victim.read_text() == '{"phase":"done","id":"planted"}'
                print("PASS:", filename, "unsafe startup rejected" if unsafe else "startup and atomic state watcher")


if __name__ == "__main__":
    main()
