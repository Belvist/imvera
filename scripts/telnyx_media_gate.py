#!/usr/bin/env python3
"""Local Telnyx media gate — bidirectional adapter without credentials."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_telnyx_codec.py",
        "tests/test_telnyx_reorder.py",
        "tests/test_telnyx_media_contract.py",
        "tests/test_telnyx_stream.py",
        "-q",
    ]
    print("telnyx-media-gate:", " ".join(cmd))
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print("telnyx-media-gate: FAILED", file=sys.stderr)
        return result.returncode
    print("telnyx-media-gate: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
