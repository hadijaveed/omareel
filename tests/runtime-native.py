#!/usr/bin/env python3
"""Actual startup Process and state watchers in native Quickshell, isolated."""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
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
            for mode in ("normal", "symlink-start", "large-start", "large-later", "symlink-later"):
                unsafe = mode.endswith("-start")
                late = mode.endswith("-later")
                work = Path(directory) / (filename + "-" + mode)
                work.mkdir(mode=0o700)
                # Broken settings must not hide Stop/state on shell startup.
                (work / "config.json").write_text("broken JSON")
                runtime = work / "omareel"
                victim = work / "victim.json"
                victim.write_text('{"phase":"done","id":"planted"}')
                if unsafe:
                    runtime.mkdir(mode=0o700)
                    if mode == "symlink-start":
                        (runtime / "state.json").symlink_to(victim)
                    else:
                        with (runtime / "state.json").open("wb") as out:
                            out.truncate(8 * 1024**3)
                shutil.copyfile(ROOT / "Omareel.js", work / "Omareel.js")
                startup = enclosing(source, 'running: true\n    stderr: StdioCollector { id: runtimeError', "Process")
                state = enclosing(source, "id: stateFile", "Process")
                watcher = enclosing(source, 'path: root.runtimeReady ? root.runtimeDir : ""', "FileView")
                command = ["bash", "-c", 'source "$1"; omarchy-shell(){ :; }; set_state done id=native-test',
                           "_", str(ROOT / "bin/omareel")]
                if late:
                    operation = ("p.unlink(); p.symlink_to(sys.argv[2])" if mode == "symlink-later"
                                 else "f=p.open('wb'); f.truncate(8*1024**3); f.close()")
                    command = [sys.executable, "-c", "import sys; from pathlib import Path; p=Path(sys.argv[1]); " + operation,
                               str(runtime / "state.json"), str(victim)]
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
        } else if (__LATE__ && root.state.phase === "error") {
          if (root.readPlanted || !root.runtimeReady) console.error("UNSAFE RUNTIME READ")
          else console.log("RUNTIME NATIVE PASS")
          Qt.quit()
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
                    .replace("__COMMAND__", json.dumps(command)).replace("__UNSAFE__", str(unsafe).lower()).replace("__LATE__", str(late).lower()))
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
                print("PASS:", filename, mode)


if __name__ == "__main__":
    main()
