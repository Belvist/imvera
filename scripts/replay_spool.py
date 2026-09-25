"""Replay the durable persist spool after a store outage.

Usage:
    python3 scripts/replay_spool.py [--spool-dir .run/spool]

Builds the real store via create_call_record_store() and re-applies
spooled writes in order. Safe to run twice (store-level idempotency).
Exit non-zero if replay stopped early (store still down).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from packages.core import create_call_record_store
from packages.core.spill import replay_spool


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--spool-dir",
        default=os.environ.get("IMVERA_PERSIST_SPOOL_DIR", str(_ROOT / ".run" / "spool")),
    )
    args = ap.parse_args()

    store = create_call_record_store()
    # Never replay through another spooling layer (would re-spill on failure).
    delegate = getattr(store, "_delegate", store)
    counts = replay_spool(args.spool_dir, delegate)
    print(f"replay: applied={counts['applied']} files_done={counts['files_done']}")
    if counts["stopped"]:
        print("replay STOPPED early — store still failing, rest left spooled")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
