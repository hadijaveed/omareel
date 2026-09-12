#!/usr/bin/env python3
"""Owner-checked settings, with locked read/merge/atomic replacement."""
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True

from runtime import MAX_JSON_BYTES, Runtime, open_base, read_limited


def object_json(data):
    try:
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError("expected an object")
        return value
    except (ValueError, UnicodeError) as error:
        raise ValueError("Invalid settings JSON; restore a valid object. The file was not replaced.") from error


def normalize(value):
    if "webcamCorner" in value:
        value["webcamPosition"] = value.pop("webcamCorner")
    return value


def merge(current, patch):
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            merge(current[key], value)
        else:
            current[key] = value
    return current


class Settings(Runtime):
    def __init__(self, path, create=False):
        path = Path(path)
        if not path.is_absolute() or ".." in path.parts or path.name in ("", ".", ".."):
            raise ValueError("settings path must be absolute without parent traversal")
        self.filename = self.name(path.name)
        # Reuse no-follow traversal and file operations, without changing the
        # permissions of the user's existing configuration directories.
        self.fd = open_base(str(path.parent), create=create)

    def value(self):
        return object_json(self.read(self.filename))

    def limit(self, name):
        self.name(name)
        return MAX_JSON_BYTES

    def update(self, action, supplied):
        with self.locked(self.filename + ".lock"):
            exists = self.inspect(self.filename)
            current = self.value() if exists else supplied
            original = json.dumps(current, sort_keys=True)
            normalize(current)
            if action == "merge":
                merge(current, normalize(supplied))
            if not exists or json.dumps(current, sort_keys=True) != original:
                self.write(self.filename, (json.dumps(current, indent=2) + "\n").encode())
                os.fsync(self.fd)
            return current


def main():
    path, action = sys.argv[1:]
    supplied = object_json(read_limited(sys.stdin.buffer, MAX_JSON_BYTES)) if action in ("ensure", "merge") else None
    store = Settings(path, create=action == "ensure")
    try:
        value = store.value() if action == "read" else store.update(action, supplied)
        print(json.dumps(value, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        print(f"Cannot use Omareel settings: {error}", file=sys.stderr)
        sys.exit(1)
