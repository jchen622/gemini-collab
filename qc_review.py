#!/usr/bin/env python3
"""Back-compatible shim. QC review is now `collab.py review <file>`.

Kept so existing notes and commands keep working.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    print("note: qc_review.py is now `collab.py review`; forwarding.\n", file=sys.stderr)
    sys.exit(subprocess.call(
        [sys.executable, str(HERE / "collab.py"), "review"] + sys.argv[1:]))
