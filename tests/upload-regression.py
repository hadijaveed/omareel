#!/usr/bin/env python3
"""Provider contracts and actual local S3 transfers. Never uses cloud accounts."""
import configparser
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
import unittest
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin/omareel"
PROVIDERS = {
    "s3": dict(region="us-east-1"),
    "r2": dict(accountId="a" * 32),
    "b2": dict(region="us-west-005"),
    "s3compat": dict(endpoint="https://objects.example.test", region="test-1"),
}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="omareel-upload-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "config.json"
        self.conf = self.root / "rclone.conf"
        self.runtime = self.root / "omareel"
        self.runtime.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("RCLONE_", "AWS_", "OMAREEL_"))}
        self.env.update(OMAREEL_CONFIG=str(self.config), RCLONE_CONFIG=str(self.conf),
                        XDG_RUNTIME_DIR=str(self.root), OMAREEL_ACCESS_KEY_ID="test-access",
                        OMAREEL_SECRET_ACCESS_KEY="test-secret",
                        RCLONE_RETRIES="1", RCLONE_LOW_LEVEL_RETRIES="1",
                        RCLONE_CONTIMEOUT="2s", RCLONE_TIMEOUT="3s")
        self.configure()

    def configure(self, provider="s3", **extra):
        self.upload = dict(provider=provider, bucket="recordings",
                           publicBase="https://videos.example.test", **PROVIDERS.get(provider, {}))
        self.upload.update(extra)
        self.config.write_text(json.dumps(dict(outputDir=str(self.root), upload=self.upload)))

    def cli(self, *args, check=True):
        return subprocess.run([str(CLI), *args], env=self.env, capture_output=True,
                              text=True, check=check, timeout=30)

    def helper(self, command, *args, check=True):
        result = subprocess.run(["bash", "-c",
            'source "$1"; shift; notify(){ :; }; omarchy-shell(){ :; }; ' + command,
            "_", str(CLI), *map(str, args)], env=self.env, capture_output=True,
            text=True, timeout=30)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def status(self):
        return json.loads(self.cli("remote", "status").stdout)

    def saved(self):
        cp = configparser.RawConfigParser()
        cp.read(self.conf)
        return cp

    def video(self):
        video = self.root / "fixture.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=64x48:rate=5:duration=1", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", str(video)], check=True, capture_output=True)
        return video


class ProviderConfig(Fixture):
    def test_all_provider_configurations(self):
        for provider, expected in {
                "s3": ("AWS", "", "us-east-1"),
                "r2": ("Cloudflare", "https://" + "a"*32 + ".r2.cloudflarestorage.com", "auto"),
                "b2": ("Other", "https://s3.us-west-005.backblazeb2.com", "us-west-005"),
                "s3compat": ("Other", "https://objects.example.test", "test-1")}.items():
            with self.subTest(provider=provider):
                self.configure(provider)
                self.cli("remote", "save")
                conf = self.saved()["omareel"]
                self.assertEqual((conf["provider"], conf["endpoint"], conf["region"]), expected)
                self.assertEqual(conf["no_check_bucket"], "true")
                self.assertEqual(conf["env_auth"], "false")
                self.assertNotIn("acl", conf)
                status = self.status()
                self.assertTrue(status["ready"])
                self.assertTrue(status["hasSecret"])
                self.assertEqual(status["backend"], "s3")
                self.assertNotIn("test-secret", json.dumps(status))
                self.assertNotIn("test-access", self.config.read_text())
                self.assertEqual(self.conf.stat().st_mode & 0o777, 0o600)

    def test_partial_credentials_do_not_silently_keep_old_values(self):
        self.cli("remote", "save")
        original = self.conf.read_bytes()
        for missing in ("OMAREEL_ACCESS_KEY_ID", "OMAREEL_SECRET_ACCESS_KEY"):
            with self.subTest(missing=missing):
                env = self.env.copy()
                self.env[missing] = ""
                result = self.cli("remote", "save", check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("both", result.stderr)
                self.assertEqual(self.conf.read_bytes(), original)
                self.env = env

    def test_blank_reuses_same_provider_but_not_another_account(self):
        self.cli("remote", "save")
        self.env.update(OMAREEL_ACCESS_KEY_ID="", OMAREEL_SECRET_ACCESS_KEY="")
        self.cli("remote", "save")
        self.configure("r2")
        self.assertFalse(self.status()["ready"])
        self.assertFalse(self.status()["hasSecret"])
        self.assertNotEqual(self.cli("remote", "save", check=False).returncode, 0)
        self.assertEqual(self.saved()["omareel"]["provider"], "AWS")

    def test_changed_region_or_endpoint_is_not_ready(self):
        for provider, changes in (("s3", dict(region="eu-west-1")),
                                  ("s3compat", dict(endpoint="https://different.example.test")),
                                  ("r2", dict(accountId="b"*32))):
            with self.subTest(provider=provider):
                self.configure(provider)
                self.cli("remote", "save")
                self.configure(provider, **changes)
                self.assertFalse(self.status()["ready"])

    def test_unrelated_remote_secret_does_not_count_and_is_preserved(self):
        self.conf.write_text("[elsewhere]\ntype = s3\nsecret_access_key = unrelated\n"
                             "[omareel]\ntype = s3\nprovider = AWS\nregion = us-east-1\n")
        self.assertFalse(self.status()["hasSecret"])
        self.cli("remote", "save")
        self.assertEqual(self.saved()["elsewhere"]["secret_access_key"], "unrelated")

    def test_malformed_config_never_leaks_secret_lines(self):
        self.conf.write_text("[omareel]\nsecret_access_key = secret-canary\nsecret_access_key = secret-canary\n")
        result = self.cli("remote", "save", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("secret-canary", result.stdout + result.stderr + json.dumps(self.status()))

    def test_existing_remote_must_exist_and_not_be_a_local_path(self):
        self.configure("existing", remote="drive:Omareel")
        self.assertFalse(self.status()["ready"])
        self.conf.write_text("[drive]\ntype = drive\n")
        self.assertTrue(self.status()["ready"])
        self.configure("existing", remote="/tmp/not-a-remote")
        self.assertFalse(self.status()["ready"])

    def test_invalid_settings_fail_before_writing_credentials(self):
        cases = [("none", {}), ("typo", {}), ("r2", {"accountId":"not-an-account"}),
                 ("b2", {"region":"https://s3.us-west-005.backblazeb2.com"}),
                 ("s3", {"region":""}), ("s3", {"bucket":"bucket/path"}),
                 ("s3", {"prefix":"../secret"}), ("s3", {"prefix":"one//two"}),
                 ("s3", {"publicBase":"javascript:alert(1)"}),
                 ("s3", {"publicBase":"https://user:password@example.test"}),
                 ("s3", {"publicBase":"https://example.test/?token=secret"}),
                 ("s3compat", {"endpoint":"objects.example.test"})]
        for provider, changes in cases:
            with self.subTest(provider=provider, changes=changes):
                self.configure(provider, **changes)
                self.assertFalse(self.status()["ready"])
                self.assertNotEqual(self.cli("remote", "save", check=False).returncode, 0)
                self.assertFalse(self.conf.exists())

    def test_existing_remote_defined_in_environment_is_supported(self):
        self.configure("existing", remote="environment:recordings")
        self.env["RCLONE_CONFIG_ENVIRONMENT_TYPE"] = "s3"
        self.assertTrue(self.status()["ready"])
        self.assertEqual(self.status()["backend"], "s3")

    def test_prefix_and_special_characters_map_to_actual_object_key(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                self.configure(provider, prefix="/team/hello & café/", publicBase="https://videos.example.test/")
                self.assertEqual(self.helper("remote_path").stdout.strip(), "omareel:recordings/team/hello & café")
                self.assertEqual(self.helper('public_object_url "$1"', 'old take #1.mp4').stdout.strip(),
                    "https://videos.example.test/team/hello%20%26%20caf%C3%A9/old%20take%20%231.mp4")

    def test_existing_base_already_refers_to_its_path(self):
        self.configure("existing", remote="drive:team/videos", prefix="ignored",
                       publicBase="https://videos.example.test/team/videos/")
        self.assertEqual(self.helper('public_object_url test.mp4').stdout.strip(),
                         "https://videos.example.test/team/videos/test.mp4")

    def test_remote_save_and_test_respect_upload_lock(self):
        with (self.runtime / "operation.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for action in ("save", "test"):
                self.assertEqual(self.cli("remote", action, check=False).returncode, 75)


class UploadFailures(Fixture):
    def setUp(self):
        super().setUp()
        self.cli("remote", "save")
        self.env["FAKE_STORE"] = str(self.root / "uploaded")
        (self.root / "uploaded").mkdir()

    mock = r'''
rclone(){
  case "$1" in
    copyto) [[ "$3" != *"$FAIL_SUFFIX" || -z "$FAIL_SUFFIX" ]] || return 9; cp "$2" "$FAKE_STORE/$(basename "$3")" ;;
    cat) cat "$FAKE_STORE/$(basename "$2")" ;;
    deletefile) [[ "$FAIL_DELETE" != true ]] || return 9; rm -f "$FAKE_STORE/$(basename "$2")" ;;
    link) [[ "$FAIL_LINK" != true ]] || return 9; printf '%s\n' "$TEST_LINK" ;;
  esac
}
curl(){
  local out=""
  while [[ $# -gt 0 ]]; do
    if [[ $1 == --output ]]; then out="$2"; shift; fi
    shift
  done
  if [[ "$BAD_BODY" == true ]]; then printf 'unrelated webpage' >"$out"
  else cp "$FAKE_STORE/"*.txt "$out"; fi
}
FAIL_SUFFIX=""; FAIL_DELETE=false; FAIL_LINK=false; BAD_BODY=false; TEST_LINK=""
sleep(){ :; };
'''

    def test_public_test_checks_content_and_always_cleans_probe(self):
        for bad in ("false", "true"):
            with self.subTest(bad=bad):
                result = self.helper(self.mock + 'BAD_BODY="$1"; cmd_remote_test', bad, check=False)
                self.assertEqual(result.returncode, 0 if bad == "false" else 1, result.stdout + result.stderr)
                self.assertFalse(list((self.root / "uploaded").iterdir()))
                self.assertFalse(list(self.runtime.glob("upload-test.*")))

    def test_delete_failure_is_not_success(self):
        result = self.helper(self.mock + "FAIL_DELETE=true; cmd_remote_test", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cleanup failed", result.stderr)
        self.assertNotIn("All good", result.stdout)

    def test_link_error_and_empty_link_fail_with_cleanup(self):
        self.configure(publicBase="")
        for fail in ("false", "true"):
            with self.subTest(fail=fail):
                result = self.helper(self.mock + 'FAIL_LINK="$1"; cmd_remote_test', fail, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(list((self.root / "uploaded").iterdir()))

    def test_thumbnail_failure_still_shares_without_broken_poster(self):
        video = self.video()
        thumb = self.root / "thumb.jpg"
        thumb.write_bytes(b"thumbnail fixture")
        result = self.helper(self.mock + 'FAIL_SUFFIX=".jpg"; upload_video "$1" "$2" Title stable-id', video, thumb)
        self.assertEqual(result.stdout.strip(), "https://videos.example.test/stable-id.html")
        html = (self.root / "uploaded/stable-id.html").read_text()
        self.assertIn('poster=""', html)
        self.assertNotIn("stable-id.jpg", html)

    def test_page_failure_falls_back_to_video_url(self):
        video = self.video()
        result = self.helper(self.mock + 'FAIL_SUFFIX=".html"; upload_video "$1" "" Title stable-id', video)
        self.assertEqual(result.stdout.strip(), "https://videos.example.test/stable-id.mp4")

    def test_changed_destination_does_not_refresh_old_share_page(self):
        video = self.video()
        result = self.helper(self.mock + r'''
append_index "$1" "https://original.example.test/stable-id.html" stable-id Old
cmd_page "$1"
''', video, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different sharing destination", result.stderr)
        self.assertFalse(list((self.root / "uploaded").iterdir()))

    def test_upload_snapshots_settings_during_transfer(self):
        video = self.video()
        self.env["ORIGINAL_CONFIG"] = str(self.config)
        result = self.helper(self.mock + r'''
eval "$(declare -f rclone | sed '1s/rclone/fake_copy/')"
rclone(){
  if [[ $1 == copyto && $3 == *.mp4 ]]; then
    jq '.upload.publicBase = "https://wrong.example.test"' "$ORIGINAL_CONFIG" >"$ORIGINAL_CONFIG.new"
    mv "$ORIGINAL_CONFIG.new" "$ORIGINAL_CONFIG"
  fi
  fake_copy "$@"
}
upload_video "$1" "" Title stable-id
''', video)
        self.assertEqual(result.stdout.strip(), "https://videos.example.test/stable-id.html")
        self.assertFalse(list(self.runtime.glob("upload-config.*")))

    def test_html_attributes_are_escaped(self):
        html = self.helper('player_page "$1" "" Title', 'https://example.test/"&').stdout
        self.assertIn("&quot;&amp;", html)


@unittest.skipUnless(shutil.which("rclone"), "rclone needed for real local S3 transfers")
class LocalS3(Fixture):
    @classmethod
    def setUpClass(cls):
        cls.server_tmp = tempfile.TemporaryDirectory(prefix="omareel-s3-server-")
        cls.store = Path(cls.server_tmp.name)
        (cls.store / "recordings").mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.endpoint = f"https://127.0.0.1:{port}"
        cls.cert = cls.store / "localhost.crt"
        key = cls.store / "localhost.key"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cls.cert), "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1"],
                       check=True, capture_output=True)
        cls.server_log = (cls.store / "server.log").open("w")
        env = {k:v for k,v in os.environ.items() if not k.startswith(("RCLONE_", "AWS_"))}
        cls.server = subprocess.Popen(["rclone", "serve", "s3", str(cls.store),
            "--addr", f"127.0.0.1:{port}", "--auth-key", "test-access,test-secret",
            "--cert", str(cls.cert), "--key", str(key),
            "--config", str(cls.store / "server.conf")], env=env,
            stdout=cls.server_log, stderr=subprocess.STDOUT)
        for _ in range(100):
            if cls.server.poll() is not None:
                cls.server_log.close()
                raise RuntimeError((cls.store / "server.log").read_text())
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.1):
                    break
            except OSError:
                time.sleep(.05)
        else:
            raise RuntimeError("Local S3 server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait(timeout=10)
        cls.server_log.close()
        cls.server_tmp.cleanup()

    def setUp(self):
        super().setUp()
        self.env.update(RCLONE_CONFIG_OMAREEL_ENDPOINT=self.endpoint,
                        RCLONE_S3_FORCE_PATH_STYLE="true", RCLONE_CA_CERT=str(self.cert),
                        CURL_CA_BUNDLE=str(self.cert))

    def test_all_provider_modes_upload_read_share_delete_via_real_s3(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                self.configure(provider, publicBase="", prefix="provider-tests/" + provider)
                self.cli("remote", "save")
                result = self.cli("remote", "test", check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("exact uploaded content", result.stdout)
                self.assertFalse(list((self.store / "recordings/provider-tests" / provider).glob("*.txt")))

    def test_all_provider_modes_multipart_metadata_and_signed_byte_ranges(self):
        video = self.video()
        with video.open("ab") as fh:
            fh.write(bytes(6 * 1024 * 1024))
        self.env.update(RCLONE_S3_UPLOAD_CUTOFF="5Mi", RCLONE_S3_CHUNK_SIZE="5Mi")
        # The local rclone server reports a whole-file MD5, not AWS's multipart
        # ETag. Adapt only this test client; production keeps rclone's checks.
        # Independently compare every downloaded byte below for every provider.
        self.env["RCLONE_S3_USE_MULTIPART_ETAG"] = "false"
        context = ssl.create_default_context(cafile=str(self.cert))
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                self.configure(provider, publicBase="", prefix="multipart/" + provider)
                self.cli("remote", "save")
                result = self.helper('upload_video "$1" "" "Multipart fixture" multipart-id', video)
                link = result.stdout.strip()
                with urlopen(link, timeout=10, context=context) as response:
                    self.assertEqual(response.read(), video.read_bytes())
                    self.assertEqual(response.headers.get_content_type(), "video/mp4")
                    self.assertEqual(response.headers["Content-Disposition"], "inline")
                    self.assertEqual(response.headers["Cache-Control"], "public, max-age=31536000")
                with urlopen(Request(link, headers={"Range":"bytes=0-127"}), timeout=10, context=context) as response:
                    # rclone serve s3 1.75 returns 200 for a partial GET, unlike real
                    # S3's 206. Check the actual range and bytes, not that server bug.
                    self.assertIn(response.status, (200, 206))
                    self.assertEqual(response.headers["Content-Range"], f"bytes 0-127/{video.stat().st_size}")
                    self.assertEqual(response.read(), video.read_bytes()[:128])

    def test_public_player_prefix_thumbnail_and_existing_remote(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        public = f"https://127.0.0.1:{port}/recordings"
        server = subprocess.Popen(["rclone", "serve", "s3", str(self.store),
            "--addr", f"127.0.0.1:{port}", "--cert", str(self.cert),
            "--dir-cache-time", "0s",
            "--key", str(self.store / "localhost.key"), "--config", str(self.store / "server.conf")],
            env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.1):
                        break
                except OSError:
                    time.sleep(.05)
            self.configure("s3compat", publicBase=public, prefix="team/hello & café")
            self.cli("remote", "save")
            self.cli("remote", "test")
            video = self.video()
            thumb = self.root / "fixture.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-frames:v", "1", str(thumb)],
                           check=True, capture_output=True)
            result = self.helper('upload_video "$1" "$2" "Title <&>" public-id', video, thumb)
            link = result.stdout.strip()
            self.assertIn("/team/hello%20%26%20caf%C3%A9/public-id.html", link)
            context = ssl.create_default_context(cafile=str(self.cert))
            with urlopen(link, context=context, timeout=10) as response:
                html = response.read().decode()
                self.assertEqual(response.headers.get_content_type(), "text/html")
                self.assertIn("Title &lt;&amp;&gt;", html)
            # The anonymous server is a separate rclone process; serve s3 keeps
            # object metadata in memory. Inspect metadata on the upload server.
            signed_page = self.helper('share_link "$1"',
                "omareel:recordings/team/hello & café/public-id.html").stdout.strip()
            with urlopen(signed_page, context=context, timeout=10) as response:
                self.assertEqual(response.headers["Content-Disposition"], "inline")
                self.assertEqual(response.headers["Cache-Control"], "public, max-age=300")
                self.assertEqual(response.read().decode(), html)
            with urlopen(link.replace(".html", ".jpg"), context=context, timeout=10) as response:
                self.assertEqual(response.read(), thumb.read_bytes())
                self.assertEqual(response.headers.get_content_type(), "image/jpeg")
            self.configure("existing", remote="omareel:recordings/team/hello & café",
                           publicBase=public + "/team/hello%20%26%20caf%C3%A9")
            self.cli("remote", "test")
        finally:
            server.terminate()
            server.wait(timeout=10)

    def test_bad_credentials_fail_instead_of_reporting_success(self):
        self.configure("s3compat", publicBase="")
        self.cli("remote", "save")
        self.env["RCLONE_CONFIG_OMAREEL_SECRET_ACCESS_KEY"] = "wrong-secret"
        result = self.cli("remote", "test", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("All good", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
