#!/usr/bin/env python3
"""Interactive text dialogue runner — same CallSession path as future voice runtime."""

from __future__ import annotations

import os
import sys

from packages.dialogue.session import CallSession


def main() -> int:
    call_id = sys.argv[1] if len(sys.argv) > 1 else "text-demo"
    session = CallSession(call_id=call_id, family_id=os.environ.get("IMVERA_FAMILY_ID", "fam-demo"))
    opening = session.start()
    print(f"Vera: {opening.validated.speech}\n")

    try:
        while True:
            line = input("You: ").strip()
            if not line:
                continue
            if line.lower() in {"/quit", "/exit", "выход"}:
                break
            result = session.handle_user_text(line)
            speech = result.validated.speech
            if speech:
                print(f"Vera: {speech}")
            print(
                f"[fsm={result.proposal.fsm_state.value} "
                f"intent={result.proposal.intent} "
                f"risk={result.safety.active_risk.value}]\n"
            )
            if session.state.is_terminal() and session.state.goodbye_confirmed:
                break
    except (KeyboardInterrupt, EOFError):
        print("\n[ended]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
