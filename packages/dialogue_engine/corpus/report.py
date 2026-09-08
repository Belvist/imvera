"""JSON corpus gate report."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from packages.dialogue_engine.corpus.runner import CorpusRunResult
from packages.dialogue_engine.corpus.schema import CorpusInvariantReport


@dataclass
class CorpusGateReport:
    corpus_version: str
    total: int
    passed: int
    failed: int
    by_wellness: dict[str, str] = field(default_factory=dict)
    opening_replays: int = 0
    planner_legacy_events: int = 0
    stale_state_mutations: int = 0
    lost_speak_effects: int = 0
    duplicate_playout_mutations: int = 0
    undelivered_question_answers: int = 0
    premature_unresolved_close: int = 0
    failed_to_goodbye_final: int = 0
    failures: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0

    @property
    def gate_passed(self) -> bool:
        return self.failed == 0 and self.total >= 500

    def to_dict(self) -> dict:
        return {
            "corpus_version": self.corpus_version,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "gate": "PASS" if self.gate_passed else "FAIL",
            "by_wellness": self.by_wellness,
            "opening_replays": self.opening_replays,
            "planner_legacy_events": self.planner_legacy_events,
            "stale_state_mutations": self.stale_state_mutations,
            "lost_speak_effects": self.lost_speak_effects,
            "duplicate_playout_mutations": self.duplicate_playout_mutations,
            "undelivered_question_answers": self.undelivered_question_answers,
            "premature_unresolved_close": self.premature_unresolved_close,
            "failed_to_goodbye_final": self.failed_to_goodbye_final,
            "elapsed_s": round(self.elapsed_s, 3),
            "failures": self.failures[:20],
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def aggregate_results(
    results: list[CorpusRunResult],
    *,
    corpus_version: str,
    category_totals: dict[str, int],
    elapsed_s: float,
) -> CorpusGateReport:
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    by_wellness: dict[str, str] = {}
    cat_pass: dict[str, int] = {k: 0 for k in category_totals}
    cat_total = dict(category_totals)

    inv = CorpusInvariantReport()
    failures: list[str] = []
    for r in results:
        cat = r.scenario_id.split("-", 1)[0]
        if r.passed:
            cat_pass[cat] = cat_pass.get(cat, 0) + 1
        else:
            failures.append(f"{r.scenario_id}: {'; '.join(r.errors[:3])}")
        inv.opening_replays += r.invariants.opening_replays
        inv.planner_legacy_events += r.invariants.planner_legacy_events
        inv.stale_state_mutations += r.invariants.stale_state_mutations
        inv.duplicate_playout_mutations += r.invariants.duplicate_playout_mutations
        inv.undelivered_question_answers += r.invariants.undelivered_question_answers
        inv.premature_unresolved_close += r.invariants.premature_unresolved_close
        inv.lost_speak_effects += r.invariants.lost_speak_effects
        inv.failed_to_goodbye_final += r.invariants.failed_to_goodbye_final

    for cat, total in cat_total.items():
        by_wellness[cat] = f"{cat_pass.get(cat, 0)}/{total}"

    return CorpusGateReport(
        corpus_version=corpus_version,
        total=len(results),
        passed=passed,
        failed=failed,
        by_wellness=by_wellness,
        opening_replays=inv.opening_replays,
        planner_legacy_events=inv.planner_legacy_events,
        stale_state_mutations=inv.stale_state_mutations,
        lost_speak_effects=inv.lost_speak_effects,
        duplicate_playout_mutations=inv.duplicate_playout_mutations,
        undelivered_question_answers=inv.undelivered_question_answers,
        premature_unresolved_close=inv.premature_unresolved_close,
        failed_to_goodbye_final=inv.failed_to_goodbye_final,
        failures=failures,
        elapsed_s=elapsed_s,
    )
