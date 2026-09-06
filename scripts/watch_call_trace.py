#!/usr/bin/env python3
"""Watch new SIP call traces during live Zoiper test."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACE_DIR = ROOT / ".run" / "traces"
OUT = ROOT / ".run" / "live-call-watch.log"


def main() -> int:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    seen: dict[str, int] = {}
    print(f"Watching {TRACE_DIR} — log: {OUT}", flush=True)
    with OUT.open("a", encoding="utf-8") as log:
        log.write(f"\n--- watch started {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        while True:
            for path in sorted(TRACE_DIR.glob("sip-*.jsonl")):
                lines = path.read_text(encoding="utf-8").splitlines()
                offset = seen.get(path.name, 0)
                for line in lines[offset:]:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    msg = f"{path.name} {row.get('type')} {json.dumps(row.get('payload', {}), ensure_ascii=False)}"
                    print(msg, flush=True)
                    log.write(msg + "\n")
                seen[path.name] = len(lines)
            time.sleep(0.5)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
