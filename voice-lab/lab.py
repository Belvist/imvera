"""Conversation Lab: text-in / text-out REPL for VERA.

Runs the REAL dialogue engine (telephony/core/dialogue.py Agent) against the
LLM daemon (MOSS_LLM_URL, default http://127.0.0.1:9500). No audio, no
telephony, no database — only "what Vera would say", so the conversation can
be tuned and gated BEFORE any voice work.

Usage (from repo root, with the runtime venv):

    "$HOME/Library/Application Support/MossVoice/runtime/qwen-venv/bin/python" \
        voice-lab/lab.py [--check-in] [--url http://127.0.0.1:9500]

REPL commands:
    plain text       -> one conversational turn
    /reset           -> fresh Agent (companion mode)
    /mode            -> print mode / status / done
    /hist            -> print the LLM history exactly as it will be sent
    /quit            -> exit
"""

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "telephony"))

from adapters.llm import LLMClient          # noqa: E402
from core.dialogue import Agent             # noqa: E402


def make_agent(url=None):
    if url:
        os.environ["MOSS_LLM_URL"] = url
    return Agent(llm=LLMClient.get())


def main():
    ap = argparse.ArgumentParser(description="Conversation Lab REPL")
    ap.add_argument("--check-in", action="store_true",
                    help="start with the service-initiated greeting")
    ap.add_argument("--url", default=None, help="LLM daemon URL override")
    args = ap.parse_args()

    agent = make_agent(args.url)
    if args.check_in:
        print(f"ВЕРА> {agent.start_check_in()}")

    print("Conversation Lab. Тип: /help для команд, /quit для выхода.")
    while True:
        try:
            line = input("ВЫ> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line == "/help":
            print("текст — реплика; /reset — новый агент; /mode — состояние; "
                  "/hist — история LLM; /quit — выход")
            continue
        if line == "/reset":
            agent = make_agent(args.url)
            if args.check_in:
                print(f"ВЕРА> {agent.start_check_in()}")
            print("(сброшено)")
            continue
        if line == "/mode":
            print(f"mode={agent.mode} step={agent.step} "
                  f"status={agent.status} done={agent.done}")
            continue
        if line == "/hist":
            for m in agent._build_history():
                print(f"[{m['role']}] {m['content'][:220]}")
            continue
        if line in ("/quit", "/exit"):
            break
        reply = agent.reply(line)
        print(f"ВЕРА> {reply}")
        if agent.done:
            print("(разговор завершён)")
            break


if __name__ == "__main__":
    main()