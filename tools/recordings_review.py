#!/usr/bin/env python3
"""Review/export call recordings — consent-gated.

Usage:
  recordings_review.py list [--since YYYY-MM-DD]
  recordings_review.py export --call-id FS-ID --out-dir /tmp/review [--override-reason TEXT]
  recordings_review.py sweep [--days N]

Export refuses calls without recorded consent unless --override-reason is
given (recorded in the bundle manifest). Retention default comes from
IMVERA_RECORDINGS_RETENTION_DAYS (30 days).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.voice_runtime.recordings import (  # noqa: E402
    DEFAULT_RETENTION_DAYS,
    export_call,
    read_catalog,
    sweep_retention,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--since", default="")
    p_exp = sub.add_parser("export")
    p_exp.add_argument("--call-id", required=True)
    p_exp.add_argument("--out-dir", required=True)
    p_exp.add_argument("--override-reason", default="")
    p_sweep = sub.add_parser("sweep")
    p_sweep.add_argument("--days", type=int, default=None)
    args = ap.parse_args()

    if args.cmd == "list":
        for row in read_catalog(since=args.since):
            print(
                f"{row.get('finalized_at', '?')} {row.get('call_id', '?')} "
                f"consent={row.get('consent')} status={row.get('family_status')} "
                f"outcome={row.get('call_outcome')} audio={len(row.get('audio_files', []))}"
            )
        return 0
    if args.cmd == "export":
        result = export_call(
            args.call_id, args.out_dir, override_reason=args.override_reason
        )
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0 if result.get("ok") else 2
    if args.cmd == "sweep":
        days = args.days
        if days is None:
            try:
                days = int(os.environ.get("IMVERA_RECORDINGS_RETENTION_DAYS", ""))
            except ValueError:
                days = DEFAULT_RETENTION_DAYS
            if not days:
                days = DEFAULT_RETENTION_DAYS
        print(json.dumps(sweep_retention(days), ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
