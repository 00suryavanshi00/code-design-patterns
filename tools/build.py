#!/usr/bin/env python3
"""Rebuild dist/code-design-patterns.skill from skill/.

The bundle is a plain zip of skill/code-design-patterns/ with the directory
itself as the top-level entry, which is what claude.ai's skill upload expects.
Entries are sorted and timestamped fixed, so the same tree always produces the
same archive — a rebuild that changes nothing produces no git diff.
"""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "skill")
OUT = os.path.join(ROOT, "dist", "code-design-patterns.skill")
EPOCH = (1980, 1, 1, 0, 0, 0)


def entries():
    for dirpath, dirnames, filenames in os.walk(SRC):
        dirnames.sort()
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            path = os.path.join(dirpath, name)
            yield path, os.path.relpath(path, SRC)


def build():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for path, arcname in entries():
            info = zipfile.ZipInfo(arcname, date_time=EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(path, "rb") as fh:
                z.writestr(info, fh.read())
    return OUT


if __name__ == "__main__":
    out = build()
    print("wrote %s (%d bytes)" % (os.path.relpath(out, ROOT), os.path.getsize(out)))
    sys.exit(0)
