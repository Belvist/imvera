"""Conversation Lab: text-in / text-out REPL for VERA (ConversationFacade).

Runs the production dialogue engine without audio or telephony.

Usage (from repo root):

    python3 voice-lab/lab.py [--url http://127.0.0.1:9500]

REPL commands:
    plain text       -> one conversational turn
    /reset           -> fresh call session
    /mode            -> print status / done
    /quit            -> exit
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "telephony"))

from conversation_system.integration.facade import ConversationFacade  # noqa: E402


def _new_session(facade: ConversationFacade, *, url: str | None = None):
    if url:
        os.environ["MOSS_LLM_URL"] = url
    call_id = uuid.uuid4().hex[:12]
    handle, greeting = facade.begin_call(call_id=call_id, greeting_played=True)
    plan0 = facade.plan_turn(handle)
    spoken0 = plan0.spoken_reply or greeting
    facade.commit_turn(handle, plan0, spoken0)
    return handle, spoken0


def main() -> None:
    ap = argparse.ArgumentParser(description="Conversation Lab REPL (facade)")
    ap.add_argument("--url", default=None, help="LLM daemon URL override")
    args = ap.parse_args()

    facade = ConversationFacade()
    handle, last = _new_session(facade, url=args.url)
    print(f"ВЕРА> {last}")
    print("Conversation Lab (facade). /help — команды, /quit — выход.")

    while True:
        try:
            line = input("Вы> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line == "/quit":
            break
        if line == "/reset":
            try:
                facade.end_call(handle)
            except Exception:  # noqa: BLE001
                pass
            handle, last = _new_session(facade, url=args.url)
            print(f"ВЕРА> {last}")
            continue
        if line == "/mode":
            print("engine=ConversationFacade")
            continue
        if line == "/help":
            print(__doc__)
            continue

        plan = facade.plan_turn(handle, transcript=line)
        reply = plan.spoken_reply or ""
        facade.commit_turn(handle, plan, reply)
        print(f"ВЕРА> {reply}")
        if plan.terminal:
            print("(звонок завершён)")
            handle, last = _new_session(facade, url=args.url)
            print(f"ВЕРА> {last}")

    try:
        facade.end_call(handle)
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    main()
