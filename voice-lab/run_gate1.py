"""Gate 1: run the 100-scenario corpus through the REAL Agent and render a
human-evaluable report.

Usage (from repo root, runtime venv):

    ".../qwen-venv/bin/python" voice-lab/run_gate1.py [--url http://127.0.0.1:9500]
    ".../qwen-venv/bin/python" voice-lab/run_gate1.py --fallback   # canned phrases only

Output: voice-lab/reports/gate1_<timestamp>.md — transcripts + the 10-point
evaluation checklist per scenario, plus a summary table.

Gate passes when >= 90 of 100 scenarios look natural to a human evaluator.
"""

import argparse
import datetime
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "telephony"))

from scenarios import SCENARIOS               # noqa: E402

CHECKLIST = [
    "не повторяется",
    "не звучит как анкета",
    "помнит контекст",
    "не хамит",
    "обращается на «вы»",
    "не использует «круто»",
    "не сюсюкает",
    "не даёт странных советов",
    "умеет менять тему",
    "умеет просто слушать",
]


def run_scenario(agent, lines):
    transcript = []
    for i, line in enumerate(lines, 1):
        reply = agent.reply(line)
        transcript.append((line, reply))
        if agent.done:
            break
    return transcript, agent


def main():
    ap = argparse.ArgumentParser(description="Gate-1 conversation corpus")
    ap.add_argument("--url", default=None, help="LLM daemon URL override")
    ap.add_argument("--fallback", action="store_true",
                    help="no LLM: canned fallback phrases only")
    args = ap.parse_args()

    # FIX: MOSS_LLM_URL is read at import time by core.dialogue — set it
    # BEFORE importing the client so --url actually redirects the run.
    if args.url:
        os.environ["MOSS_LLM_URL"] = args.url
    from adapters.llm import LLMClient            # noqa: E402
    from core.dialogue import Agent               # noqa: E402

    rows = []
    for sid, cat, lines in SCENARIOS:
        llm = None if args.fallback else LLMClient.get()
        agent = Agent(llm=llm)
        transcript, agent = run_scenario(agent, lines)
        rows.append((sid, cat, transcript, agent))

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(os.path.join(_HERE, "reports"), exist_ok=True)
    path = os.path.join(_HERE, "reports", f"gate1_{ts}.md")

    with open(path, "w", encoding="utf-8") as f:
        f.write("# Gate 1 — 100 разговоров\n\n")
        f.write(f"Дата: {ts}  ·  режим: "
                f"{'fallback-фразы (без LLM)' if args.fallback else 'LLM'}\n\n")
        f.write("## Сводка\n\n")
        f.write("| # | категория | ходов | вердикт | done |\n")
        f.write("|---|-----------|-------|---------|------|\n")
        for sid, cat, transcript, agent in rows:
            f.write(f"| {sid} | {cat} | {len(transcript)} | "
                    f"{agent.status} | {agent.done} |\n")

        f.write("\n## Оценка (чек-лист)\n\n")
        f.write("| # | категория | " + " | ".join(CHECKLIST) + " |\n")
        f.write("|---|-----------|" + "|".join(["---"] * len(CHECKLIST)) + "|\n")
        for sid, cat, _t, _a in rows:
            f.write(f"| {sid} | {cat} | " + " | ".join(["[ ]"] * len(CHECKLIST))
                    + " |\n")

        for sid, cat, transcript, agent in rows:
            f.write(f"\n## {sid}. {cat}  "
                    f"(verdict={agent.status}, done={agent.done}, "
                    f"mode={agent.mode})\n\n")
            for user, reply in transcript:
                f.write(f"**Ч:** {user}\n\n")
                f.write(f"**В:** {reply}\n\n")

    print(f"Report: {path}")
    print(f"Scenarios: {len(rows)}  ·  done={sum(1 for r in rows if r[3].done)} "
          f"·  ok={sum(1 for r in rows if r[3].status == 'ok')} "
          f"·  attention={sum(1 for r in rows if r[3].status == 'attention')} "
          f"·  alert={sum(1 for r in rows if r[3].status == 'alert')}")


if __name__ == "__main__":
    main()