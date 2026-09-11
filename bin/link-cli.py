#!/usr/bin/env python3
"""Create the CLI shortcut only when explicitly requested by setup/link."""
import os
from pathlib import Path
import stat
import sys


def check_directory(fd):
    info = os.fstat(fd)
    if info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise ValueError("CLI directories must belong to you and not be group/world-writable")


def install(source, home):
    source = str(Path(source).resolve(strict=True))
    # Keep operations anchored to checked directory descriptors. Never follow
    # a redirected .local/bin, replace an entry, or install inside a symlink
    # to a directory named 'omareel'. Existing links are inspected with lstat.
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(home, flags)
    try:
        check_directory(fd)
        for name in (".local", "bin"):
            try:
                os.mkdir(name, mode=0o755, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(name, flags, dir_fd=fd)
            os.close(fd)
            fd = child
            check_directory(fd)
        try:
            os.symlink(source, "omareel", dir_fd=fd)
        except FileExistsError:
            info = os.stat("omareel", dir_fd=fd, follow_symlinks=False)
            if info.st_uid != os.geteuid() or not stat.S_ISLNK(info.st_mode):
                raise ValueError("existing omareel entry is not a symlink owned by you")
            existing = os.readlink("omareel", dir_fd=fd)
            if os.path.normpath(os.path.join(home, ".local", "bin", existing)) != source:
                raise ValueError("existing omareel symlink points elsewhere")
    finally:
        os.close(fd)


def main():
    source, home = sys.argv[1:]
    target = os.path.join(home, ".local", "bin", "omareel")
    try:
        install(source, home)
    except (OSError, ValueError) as error:
        print(f"Cannot link {target}: {error}. No existing entry was replaced. "
              "Inspect the path and its ownership before retrying; do not use sudo.", file=sys.stderr)
        return 1
    print(f"Linked {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
