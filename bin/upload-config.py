#!/usr/bin/env python3
"""Validated upload destinations. Never print or put credentials in argv."""
import configparser
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote, urlsplit


MANAGED = {"s3", "r2", "b2", "s3compat"}


def web_url(value, label):
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or any(c.isspace() or ord(c) < 32 for c in value)):
        raise ValueError(f"{label} must be an http(s) URL without credentials, query or fragment")
    return value


def destination(upload):
    provider = upload.get("provider", "none")
    base = upload.get("publicBase", "").strip()
    base = web_url(base, "Public URL") if base else ""
    if provider == "none":
        raise ValueError("No upload destination selected")
    if provider == "existing":
        remote = upload.get("remote", "").strip().rstrip("/")
        if not re.fullmatch(r"[\w][\w .-]*:[^\x00-\x1f]*", remote):
            raise ValueError("Choose an existing rclone remote as name:path (not a local path)")
        return remote, base, {}
    if provider not in MANAGED:
        raise ValueError("Unknown upload provider")
    bucket = upload.get("bucket", "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        raise ValueError("Enter a bucket name (3–63 lowercase letters, numbers, dots or hyphens; no path)")
    prefix = upload.get("prefix", "").strip().strip("/")
    if any(p in {".", "..", ""} for p in prefix.split("/")) and prefix:
        raise ValueError("Folder must not contain empty, '.' or '..' path components")
    if any(ord(c) < 32 for c in prefix) or "\\" in prefix:
        raise ValueError("Folder contains an unsupported character")
    region = upload.get("region", "").strip()
    values = {"type": "s3", "provider": "Other", "endpoint": "", "region": region}
    if provider == "r2":
        account = upload.get("accountId", "").strip()
        if not re.fullmatch(r"[a-fA-F0-9]{32}", account):
            raise ValueError("Cloudflare account ID must contain 32 hexadecimal characters")
        values.update(provider="Cloudflare", region="auto",
                      endpoint=f"https://{account.lower()}.r2.cloudflarestorage.com")
    elif provider == "s3":
        if not re.fullmatch(r"[a-z0-9-]+", region):
            raise ValueError("AWS region is required (e.g. us-east-1)")
        values["provider"] = "AWS"
    elif provider == "b2":
        if not re.fullmatch(r"[a-z]{2}-[a-z]+-\d{3}", region):
            raise ValueError("Backblaze region is required (e.g. us-west-004, from the S3 endpoint)")
        values["endpoint"] = f"https://s3.{region}.backblazeb2.com"
    else:
        values["endpoint"] = web_url(upload.get("endpoint", ""), "Endpoint")
        if region and not re.fullmatch(r"[a-zA-Z0-9-]+", region):
            raise ValueError("Invalid S3-compatible region")
    remote = f"omareel:{bucket}" + (f"/{prefix}" if prefix else "")
    if base and prefix:
        base += "/" + quote(prefix, safe="/")
    return remote, base, values


def read_remotes(path):
    cp = configparser.RawConfigParser()
    cp.read(path)
    return cp


def credentials_match(cp, expected):
    if not cp.has_section("omareel"):
        return False
    section = cp["omareel"]
    return (all(section.get(k, "").rstrip("/") == v.rstrip("/") for k, v in expected.items())
            and bool(section.get("access_key_id", "").strip())
            and bool(section.get("secret_access_key", "").strip()))


def status(upload, path):
    result = dict(provider=upload.get("provider", "none"), remote="", base="", config=upload,
                  hasSecret=False, ready=False, rcloneInstalled=bool(shutil.which("rclone")), message="")
    try:
        remote, base, expected = destination(upload)
        result.update(remote=remote, base=base)
        if not result["rcloneInstalled"]:
            raise ValueError("rclone is not installed: sudo pacman -S rclone")
        if expected:
            cp = read_remotes(path)
            result["backend"] = cp.get("omareel", "type", fallback="")
            result["hasSecret"] = credentials_match(cp, expected)
            if not result["hasSecret"]:
                raise ValueError("Save credentials for this provider/account/region first")
        else:
            # Let rclone resolve existing remotes, including encrypted configs
            # unlocked by RCLONE_CONFIG_PASS and environment-defined remotes.
            listed = subprocess.run(["rclone", "listremotes", "--json", "--config", str(path),
                                     "--ask-password=false"], capture_output=True, text=True, timeout=5)
            if listed.returncode:
                raise ValueError("Cannot load existing remotes; check rclone config/unlock settings")
            name = remote.split(":", 1)[0]
            match = next((r for r in json.loads(listed.stdout) if r["name"] == name), None)
            if not match:
                raise ValueError("That rclone remote does not exist in the configured rclone file/environment")
            result["backend"] = match["type"]
        result["ready"] = True
    except (ValueError, OSError, configparser.Error, subprocess.TimeoutExpired) as exc:
        # ConfigParser errors may contain entire credential lines. Never surface them.
        result["message"] = str(exc) if isinstance(exc, ValueError) else "Cannot read rclone config (plain-text config required)"
    return result


def save(upload, path):
    _, _, expected = destination(upload)
    if not expected:
        return "Existing remotes are managed by rclone config"
    key = os.environ.get("OMAREEL_ACCESS_KEY_ID", "").strip()
    secret = os.environ.get("OMAREEL_SECRET_ACCESS_KEY", "").strip()
    if bool(key) != bool(secret):
        raise ValueError("Enter both access key and secret together, or leave both blank to keep them")
    if any(ord(c) < 32 for c in key + secret):
        raise ValueError("Credentials must not contain control characters")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".omareel.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cp = read_remotes(path)
        match = credentials_match(cp, expected)
        if not key and not match:
            raise ValueError("Enter both credentials for this provider/account/region; old credentials cannot be reused")
        if not match:
            cp.remove_section("omareel")
            cp.add_section("omareel")
        if key:
            cp.set("omareel", "access_key_id", key)
            cp.set("omareel", "secret_access_key", secret)
            cp.remove_option("omareel", "session_token")
        for name, value in dict(expected, no_check_bucket="true", env_auth="false").items():
            cp.set("omareel", name, value)
        # Bucket policy controls visibility. B2 rejects canned private ACLs;
        # modern AWS buckets disable ACLs, and R2 does not implement them.
        cp.remove_option("omareel", "acl")
        fd, tmp = tempfile.mkstemp(prefix=".omareel-", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as fh:
                os.fchmod(fh.fileno(), 0o600)
                cp.write(fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return f"Saved rclone remote 'omareel' ({expected['provider']})"


def main():
    action, config, conf, *args = sys.argv[1:]
    upload = json.loads(Path(config).read_text()).get("upload", {})
    path = Path(conf)
    if action == "status":
        print(json.dumps(status(upload, path)))
    elif action == "save":
        print(save(upload, path))
    elif action == "validate":
        result = status(upload, path)
        if not result["ready"]:
            raise ValueError(result["message"])
    else:
        remote, base, _ = destination(upload)
        if action == "path":
            print(remote)
        elif action == "base":
            print(base)
        elif action == "url":
            print(base + "/" + quote(args[0], safe="") if base else "")
        else:
            raise ValueError("Unknown upload helper action")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, configparser.Error) as exc:
        print(str(exc) if isinstance(exc, ValueError) else "Cannot read/write upload configuration", file=sys.stderr)
        sys.exit(1)
