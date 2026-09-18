#!/usr/bin/env python3
"""Checked, bounded recording-library reads and atomic writes."""
import contextlib
import json
import os
from pathlib import Path
import sys
import tempfile

from runtime import Runtime, open_base, read_limited, MAX_FILE_BYTES, MAX_JSON_BYTES
from studio import run


class Index(Runtime):
    def __init__(self, directory):
        self.fd = open_base(str(directory))

    def data(self):
        try:
            data = self.read("index.jsonl")
        except FileNotFoundError:
            return b""
        for line in data.splitlines():
            if len(line) > MAX_JSON_BYTES:
                raise ValueError("Recording index entry exceeds its byte limit")
        return data

    def update(self, action, file, args):
        with self.locked("index.lock"):
            data = self.data()
            if action == "append":
                entry = read_limited(sys.stdin.buffer, MAX_JSON_BYTES)
                if not isinstance(json.loads(entry), dict):
                    raise ValueError("Invalid recording index entry")
                result = data.rstrip(b"\n") + (b"\n" if data else b"") + entry.rstrip(b"\n") + b"\n"
            else:
                if not data:
                    return
                query, *extra = args
                with tempfile.TemporaryFile() as source:
                    source.write(data)
                    source.seek(0)
                    expression = query if action == "rewrite" else "if .file == $file then (" + query + ") else . end"
                    result = run(["jq", "-c", "--arg", "file", file, *extra, expression],
                                 30, input_file=source, stdout_limit=MAX_FILE_BYTES)
            if any(len(line) > MAX_JSON_BYTES for line in result.splitlines()):
                raise ValueError("Recording index entry exceeds its byte limit")
            self.write("index.jsonl", result)
            os.fsync(self.fd)


def main():
    action, file, *args = sys.argv[1:]
    try:
        store = Index(Path(file).parent)
    except FileNotFoundError:
        # A fresh installation has no recording directory yet. Reading its
        # empty library must not create folders or show a startup error.
        if action in ("list", "entry"):
            return
        raise
    with contextlib.closing(store) as index:
        if action in ("patch", "append", "rewrite"):
            index.update(action, file, args)
        elif action == "list":
            sys.stdout.buffer.write(index.data())
        elif action in ("entry", "last"):
            latest = None
            for line in index.data().splitlines():
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict) and (action == "last" or entry.get("file") == file):
                    latest = entry
            if latest is not None:
                print(json.dumps(latest))
            elif action == "last":
                sys.exit(1)
        else:
            raise ValueError("Unknown recording index action")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        print("Recording library: " + str(error), file=sys.stderr)
        sys.exit(1)
