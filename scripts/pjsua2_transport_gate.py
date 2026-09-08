#!/usr/bin/env python3
"""CLI for Phase B PJSUA2 transport gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.pjsua2_blackbox_caller.transport_gate import main

if __name__ == "__main__":
    raise SystemExit(main())
