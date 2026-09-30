"""Cut 3b: the engine path never loads the legacy planner module.

Extends Cut 3a (never *calls* Planner) to imports: on an engine-driven
call, `packages.dialogue.planner` must stay out of `sys.modules` —
decisions, loading, everything. Runs in a fresh interpreter because
imports are process-global; flag-off parity tests still load it there.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.dialogue_engine

_PROBE = (
    "import os, sys; "
    "os.environ['IMVERA_DIALOGUE_ENGINE'] = '1'; "
    "from packages.voice_runtime import call_actor as _ca; "
    "from packages.dialogue.session import CallSession; "
    "from packages.core.memory_store import InMemoryCallRecordStore; "
    "from packages.dialogue_engine.scenario_runner import ScenarioRunner; "
    "from packages.dialogue_engine.events import CallStarted; "
    "from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text; "
    "r = ScenarioRunner(call_id='no-planner', elder_display_name='Тест'); "
    "r.run([CallStarted(), 'Хорошо.', 'Внучка приезжала, хорошо посидели.']); "
    "s = CallSession(call_id='no-planner-s', family_id='fam', store=InMemoryCallRecordStore()); "
    "assert s.uses_dialogue_engine(); "
    "t = build_rich_turn_from_text('Хорошо.', utterance_id='u-1'); "
    "res = s.handle_user_text('Хорошо.', utterance_id='u-1', rich_turn=t); "
    "assert res.from_engine; "
    "loaded = sorted(m for m in sys.modules if m == 'packages.dialogue.planner'); "
    "print('PLANNER_LOADED:' + ','.join(loaded)); "
    "assert loaded == [], loaded; "
)


def test_engine_path_never_loads_legacy_planner() -> None:
    proc = subprocess.run(
        [sys.executable, "-B", "-c", _PROBE],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "PLANNER_LOADED:" in proc.stdout, proc.stdout[-500:] + proc.stderr[-500:]
