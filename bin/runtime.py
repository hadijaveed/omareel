#!/usr/bin/env python3
"""Private runtime storage. All named file access is relative to checked FDs."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import time


DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
KNOWN_FILES = ("state.json", "state.lock", "operation.lock", "omareel.log", "gsr.pid", "cam.pid")


def check_owner(info, directory=False):
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError("runtime entries must be owned by the current user and have the expected type")
    # An opened reader may observe link count zero after an atomic replacement.
    # It still holds the previous complete file; multiple links are unsafe.
    if info.st_mode & 0o022 or (not directory and info.st_nlink > 1):
        raise ValueError("runtime entries must not be writable by others or hard-linked")


def open_base(path, create=False):
    if not path or not os.path.isabs(path):
        raise ValueError("XDG_RUNTIME_DIR must name an absolute, user-owned session directory; no /tmp fallback")
    fd = os.open("/", DIRECTORY_FLAGS)
    try:
        # Check every component, including symlinks earlier in XDG_RUNTIME_DIR.
        # A sticky system temp directory may contain a private test/session dir.
        parts = Path(path).parts[1:]
        if not parts or ".." in parts:
            raise ValueError("invalid XDG_RUNTIME_DIR")
        for part in parts:
            info = os.fstat(fd)
            if info.st_uid not in (0, os.geteuid()) or (
                info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX)
            ):
                raise ValueError("unsafe ancestor of XDG_RUNTIME_DIR")
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        check_owner(os.fstat(fd), directory=True)
        return fd
    except BaseException:
        os.close(fd)
        raise


class Runtime:
    def __init__(self, base=None):
        self.base = base if base is not None else os.environ.get("XDG_RUNTIME_DIR", "")
        parent = open_base(self.base)
        try:
            try:
                os.mkdir("omareel", 0o700, dir_fd=parent)
            except FileExistsError:
                pass
            self.fd = os.open("omareel", DIRECTORY_FLAGS, dir_fd=parent)
        finally:
            os.close(parent)
        try:
            check_owner(os.fstat(self.fd), directory=True)
            # Older releases created an owned 0755 directory. Tighten it only
            # after verifying ownership, type and absence of shared write access.
            os.fchmod(self.fd, 0o700)
        except BaseException:
            self.close()
            raise

    def close(self):
        os.close(self.fd)

    @staticmethod
    def name(name):
        if not name or name in (".", "..") or "/" in name:
            raise ValueError("runtime file name must be a single path component")
        return name

    def inspect(self, name):
        try:
            info = os.stat(self.name(name), dir_fd=self.fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        check_owner(info)
        return True

    def open(self, name, flags, create=False):
        name = self.name(name)
        flags |= os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        if create:
            try:
                fd = os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=self.fd)
            except FileExistsError:
                fd = os.open(name, flags, dir_fd=self.fd)
        else:
            fd = os.open(name, flags, dir_fd=self.fd)
        try:
            check_owner(os.fstat(fd))
            return fd
        except BaseException:
            os.close(fd)
            raise

    @contextlib.contextmanager
    def locked(self, name, nonblocking=False):
        fd = self.open(name, os.O_RDWR, create=True)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0))
            yield
        finally:
            os.close(fd)

    def read(self, name):
        with os.fdopen(self.open(name, os.O_RDONLY), "rb") as source:
            return source.read()

    def write(self, name, data):
        self.inspect(name)
        temporary = ".write-" + secrets.token_hex(16)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=self.fd)
        try:
            with os.fdopen(fd, "wb") as destination:
                destination.write(data)
                destination.flush()
                os.fsync(destination.fileno())
            self.inspect(name)
            os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=self.fd)
            except FileNotFoundError:
                pass

    def initialize(self):
        for name in KNOWN_FILES:
            self.inspect(name)
        with self.locked("state.lock"):
            if not self.inspect("state.json"):
                self.write("state.json", json.dumps({"phase": "idle", "updatedAt": int(time.time())}).encode())


def main():
    runtime = Runtime()
    try:
        action, *args = sys.argv[1:]
        if action == "init":
            runtime.initialize()
            print(os.path.join(runtime.base, "omareel"))
        elif action == "read":
            sys.stdout.buffer.write(runtime.read(args[0]))
        elif action == "write":
            data = sys.stdin.buffer.read()
            if args[0] == "state.json":
                if not isinstance(json.loads(data), dict):
                    raise ValueError("state must be a JSON object")
                with runtime.locked("state.lock"):
                    runtime.write(args[0], data)
            else:
                runtime.write(args[0], data)
        elif action == "append":
            fd = runtime.open(args[0], os.O_WRONLY | os.O_APPEND, create=True)
            try:
                os.fchmod(fd, 0o600)
                while data := os.read(0, 65536):
                    view = memoryview(data)
                    while view:
                        view = view[os.write(fd, view):]
            finally:
                os.close(fd)
        elif action == "locked":
            with runtime.locked("operation.lock", nonblocking=True):
                # The child cannot inherit the lock; background recorder/camera
                # processes must never retain it and prevent a later Stop.
                return subprocess.call(args, env=dict(os.environ, OMAREEL_OPERATION_LOCKED="1"), close_fds=True)
        else:
            raise ValueError("unknown runtime operation")
        return 0
    finally:
        runtime.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BlockingIOError:
        sys.exit(75)
    except (OSError, ValueError) as error:
        print(f"Omareel runtime unavailable: {error}. No unsafe entry was replaced. "
              "Run from your desktop session and inspect the runtime path; do not use sudo.", file=sys.stderr)
        sys.exit(1)
