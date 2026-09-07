#!/usr/bin/env python3
"""Plain-text policy plus real Qt rendering/network regression. No cloud/device access.

Requires Qt 6 qmltestrunner, QtTest, QtQuick and QtQuick.Controls. Theme/border
stubs replace shell-only dependencies; production Hint, result handler and
device controls are loaded from source without changing their text behavior.
"""
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]


def block(source, marker):
    """Extract a balanced QML/JS block, ignoring braces inside strings/comments."""
    start = source.index("{", source.index(marker))
    tokens = re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/|[{}]', source[start:])
    depth = 0
    for token in tokens:
        if token[0] == "{":
            depth += 1
        elif token[0] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1:start + token.start()]
    raise AssertionError("Unclosed block: " + marker)


class TextSecurity(unittest.TestCase):
    def test_every_owned_text_sink_is_explicitly_plain(self):
        count = 0
        for path in ROOT.glob("*.qml"):
            source = path.read_text()
            for match in re.finditer(r"\b(?:Text|Label|TextEdit|TextArea)\s*\{", source):
                with self.subTest(file=path.name, offset=match.start()):
                    body = block(source[match.start():], match[0])
                    self.assertRegex(body, r"\btextFormat:\s*Text\.PlainText\b")
                    self.assertEqual(len(re.findall(r"\btextFormat\s*:", body)), 1)
                    count += 1
        self.assertGreaterEqual(count, 18)
        bar = (ROOT / "BarWidget.qml").read_text()
        self.assertNotRegex(bar, r"\b(?:Dropdown|Toggle)\s*\{")
        # Shared Button tooltips do not expose textFormat. Keep their text
        # independent of config/process data; the destination remains in Hint.
        self.assertIn('tooltipText: "Upload and copy the share link"', bar)
        self.assertNotRegex(bar, r"tooltipText:.*(?:root\.message|uploadSummary)")

    def test_endpoint_error_literal_rendering_and_no_image_fetch(self):
        runner = os.environ.get("QMLTESTRUNNER") or shutil.which("qmltestrunner")
        if not runner:
            runner = next((str(p) for p in (Path("/usr/lib/qt6/bin/qmltestrunner"),
                                           Path("/usr/lib/qt6/libexec/qmltestrunner")) if p.exists()), None)
        self.assertIsNotNone(runner, "Install Qt 6 declarative dev tools and QML QtTest/Quick/Controls modules")
        requests = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml")
                self.end_headers()
                self.wfile.write(b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8"/></svg>')

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = "http://127.0.0.1:" + str(server.server_port)
        payload = '<img src="' + base + '/blocked-image"> <b>endpoint error & device</b>'
        with tempfile.TemporaryDirectory(prefix="omareel-text-security-") as directory:
            temp = Path(directory)
            config = temp / "config.json"
            config.write_text(json.dumps({"outputDir": directory}))
            env = {k: v for k, v in os.environ.items() if not k.startswith(("OMAREEL_", "RCLONE_", "AWS_"))}
            env.update(OMAREEL_CONFIG=str(config), XDG_RUNTIME_DIR=directory,
                       RCLONE_CONFIG=str(temp / "unused-rclone.conf"), TEST_ERROR=payload,
                       QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
            # Run the actual remote-test failure path with a simulated rclone
            # error. No remote validation, real credentials or transfers occur.
            result = subprocess.run(["bash", "-c", '''
source "$1"
upload_config(){ :; }
remote_path(){ printf 'fixture:bucket'; }
public_base(){ :; }
rclone_run(){
  if [[ $1 == copyto ]]; then printf '%s\n' "$TEST_ERROR" >&2; return 1; fi
  return 0
}
cmd_remote_test
''', "_", str(ROOT / "bin/omareel")], env=env, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stderr.strip(), "Upload failed: " + payload)
            bar = (ROOT / "BarWidget.qml").read_text()
            hint = "Text {" + block(bar, "component Hint: Text") + "}"
            handler = block(bar[bar.index("id: testProc"):], "onExited: function(code)")
            shutil.copytree(ROOT / "tests/text-fixture", temp / "fixture")
            for name in ("PlainDropdown.qml", "PlainToggle.qml"):
                shutil.copyfile(ROOT / name, temp / "fixture" / name)
            (temp / "fixture/Hint.qml").write_text("import QtQuick\nimport qs.Commons\n" + hint)
            template = (temp / "fixture/tst_render.qml").read_text()
            template = template.replace("__STDERR__", json.dumps(result.stderr))
            template = template.replace("__STDOUT__", json.dumps(result.stdout))
            template = template.replace("__PAYLOAD__", json.dumps(payload))
            template = template.replace("__BASE__", json.dumps(base))
            template = template.replace("__HANDLER__", handler)
            (temp / "fixture/tst_render.qml").write_text(template)
            run = subprocess.run([runner, "-input", str(temp / "fixture"),
                                  "-import", str(temp / "fixture/imports")],
                                 env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertNotRegex(run.stderr, r"(?:ReferenceError|TypeError|Unable to assign)")
            self.assertIn("/control-image", requests, "Positive control must demonstrate that image fetching works")
            self.assertFalse([p for p in requests if p != "/control-image"], requests)
            print("Qt rendered the real upload error literally; protected sinks made zero requests; AutoText control fetched once.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
