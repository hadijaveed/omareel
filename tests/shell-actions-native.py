#!/usr/bin/env python3
"""Exercise production Stop handlers with native Quickshell process execution.

Run on each supported Omarchy/Quickshell version before release. Offscreen;
only a temporary argv recorder is launched, never real devices or shell actions.
"""
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
block = runpy.run_path(str(ROOT / "tests/text-security.py"))["block"]


def main():
    if not shutil.which("quickshell"):
        raise SystemExit("Requires native Quickshell; run on each supported Omarchy version.")
    with tempfile.TemporaryDirectory(prefix="omareel-shell-actions-") as directory:
        temp = Path(directory)
        injected = temp / "must-not-exist"
        title = f"spaces ' quotes ; $(touch {injected}) `touch {injected}`"
        for filename in ("BarWidget.qml", "Panel.qml"):
            source = (ROOT / filename).read_text()
            action = re.search(r'text:\s*"Stop(?: & save)?"[\s\S]*?onClicked:\s*([^\n]+)', source)
            assert action, "Missing production Stop handler in " + filename
            handler = action[1].strip()
            body = block(source, "function cliRun(")
            work = temp / filename
            work.mkdir()
            output = work / "argv.jsonl"
            executable = work / "argv recorder ' test"
            executable.write_text("#!/usr/bin/env python3\nimport json,os,sys\n"
                + "fd=os.open(" + repr(str(output)) + ",os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)\n"
                + "os.write(fd,(json.dumps(sys.argv[1:])+'\\n').encode())\nos.close(fd)\n")
            executable.chmod(0o700)
            (work / "shell.qml").write_text('''import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
ShellRoot {
  Item {
    id: root
    property string cli: __CLI__
    function close() {}
    function cliRun(args) { __BODY__ }
    Button {
      id: stopButton
      onClicked: __HANDLER__
    }
    Component.onCompleted: {
      stopButton.clicked()
      cliRun(["upload", "last", __TITLE__])
    }
  }
  FileView {
    id: result
    path: __OUTPUT__
    printErrors: false
    onLoaded: {
      if (text().trim().split("\\n").length === 2) {
        console.log("SHELL ACTIONS PASS")
        Qt.quit()
      }
    }
  }
  Timer { interval: 50; running: true; repeat: true; onTriggered: result.reload() }
  Timer { interval: 5000; running: true; onTriggered: { console.error("SHELL ACTIONS TIMEOUT"); Qt.quit() } }
}
'''.replace("__CLI__", json.dumps(str(executable))).replace("__BODY__", body)
                .replace("__HANDLER__", handler).replace("__TITLE__", json.dumps(title))
                .replace("__OUTPUT__", json.dumps(str(output))))
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       QT_QUICK_CONTROLS_STYLE="Basic", QT_QPA_PLATFORMTHEME="",
                       XDG_RUNTIME_DIR=str(work), XDG_CACHE_HOME=str(work / "cache"))
            result = subprocess.run(["quickshell", "-p", str(work), "--no-color"], env=env,
                                    capture_output=True, text=True, timeout=12)
            logs = result.stdout + result.stderr
            assert result.returncode == 0 and "SHELL ACTIONS PASS" in logs, logs
            for error in ("ReferenceError", "TypeError", "Failed to load configuration", "SHELL ACTIONS TIMEOUT"):
                assert error not in logs, logs
            received = [json.loads(line) for line in output.read_text().splitlines()]
            assert sorted(received) == sorted([["stop"], ["upload", "last", title]]), received
            assert not injected.exists(), "Arguments were interpreted by a shell"
            print("PASS:", filename, "native Stop signal, detached execution, literal arguments")


if __name__ == "__main__":
    main()
