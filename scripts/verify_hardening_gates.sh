#!/usr/bin/env bash
# MossVoice hardening gate verifier — exit 0 only if all checks pass.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REPORT="${ROOT}/docs/VERIFICATION_GATE_REPORT.md"
FAIL=0
SECTIONS=()

log_section() {
  SECTIONS+=("$1")
  echo ""
  echo "=== $1 ==="
}

grep_must_be_empty() {
  local label="$1"
  local pattern="$2"
  local path="$3"
  if grep -rn "$pattern" $path 2>/dev/null | grep -v __pycache__ | grep -v '.pyc:'; then
    echo "FAIL: $label — pattern found"
    FAIL=1
    return 1
  fi
  echo "PASS: $label (0 matches)"
  return 0
}

grep_must_exist() {
  local label="$1"
  local pattern="$2"
  local path="$3"
  if ! grep -rn "$pattern" $path 2>/dev/null | grep -v __pycache__ | head -1; then
    echo "FAIL: $label — pattern missing"
    FAIL=1
    return 1
  fi
  echo "PASS: $label"
  return 0
}

# --- Baseline greps (sections A–J) ---
log_section "A — Stream consumption (no early break in for-delta)"
grep_must_exist "reply_segments exists" "def reply_segments" telephony/core/events.py
grep_must_exist "keep reading LLM stream comment" "Keep reading the LLM stream" telephony/core/events.py
grep_must_exist "tail flush after stream" "flush a trailing reply" telephony/core/events.py
if [[ -f telephony/tests/test_reply_segments_stream_consumption.py ]]; then
  echo "PASS: stream consumption test file exists"
else
  echo "FAIL: stream consumption test file missing"
  FAIL=1
fi

log_section "B — QuestionLedger"
grep_must_exist "QuestionLedger" "class QuestionLedger" telephony/conversation_system/
grep_must_exist "QuestionRecord" "class QuestionRecord" telephony/conversation_system/
grep_must_exist "GENERATED status" "GENERATED" telephony/conversation_system/ledger/question_ledger.py
grep_must_exist "segment ledger" "class SegmentLedger" telephony/conversation_system/ledger/segment_ledger.py

log_section "C — Exact required_slot (no bundled mood/sleep/plans)"
grep_must_be_empty "no bundled slot phrase" "настроении, сне или планах" telephony/

log_section "D — Interruption stack (SIDE_ANSWER guard)"
grep_must_exist "_no_interrupt_resume" "_no_interrupt_resume" telephony/conversation_system/policy/fsm.py
if [[ -f telephony/tests/test_side_question_no_listen_reset.py ]]; then
  echo "PASS: side question test file exists"
else
  echo "FAIL: side question test file missing"
  FAIL=1
fi

log_section "E — TurnDirective dataclass"
grep_must_exist "TurnDirective" "class TurnDirective" telephony/conversation_system/domain/turn_directive.py
grep_must_be_empty "no next_directive or merge" "next_directive or" telephony/conversation_system/runtime/session.py

log_section "F — Semantic output validator"
grep_must_exist "slot mismatch" "_slot_mismatch" telephony/conversation_system/reply/spoken.py
if [[ -f telephony/tests/test_semantic_slot_validator.py ]]; then
  echo "PASS: semantic slot test file exists"
else
  echo "FAIL: semantic slot test file missing"
  FAIL=1
fi

log_section "G — RECORD_NOTIFY arbitration"
grep_must_exist "critical phases" "_PROCESS_CRITICAL_PHASES" telephony/conversation_system/runtime/session.py
grep_must_exist "record notify resolver guard" "CallPhase.RECORD_NOTIFY" telephony/conversation_system/policy/resolver.py

log_section "H — Actual Heard (segment lifecycle)"
grep_must_exist "mark_segment_played" "def mark_segment_played" telephony/conversation_system/runtime/session.py
grep_must_exist "SEGMENT_PLAYED event" "SEGMENT_PLAYED" telephony/conversation_system/ledger/event_log.py
grep_must_exist "orchestrator playback callback" "mark_segment_played_for_call" telephony/core/orchestrator.py

log_section "I — Qwen3 TTS true stream"
grep_must_exist "_http_ndjson_stream" "_http_ndjson_stream" telephony/moss_providers.py
if grep -q "test_stream_barrier" telephony/tests/test_providers.py 2>/dev/null; then
  echo "PASS: barrier stream test"
else
  echo "FAIL: barrier stream test missing"
  FAIL=1
fi

log_section "J — MOSS_LOCAL_ONLY"
grep_must_exist "enforce_local_only" "def enforce_local_only" telephony/adapters/cloud.py
grep_must_exist "LocalProviderFactory" "class LocalProviderFactory" telephony/adapters/cloud.py
grep_must_exist "startup enforce" "enforce_local_only" telephony/core/orchestrator.py

log_section "K — Model identity in /health"
grep_must_exist "build_info phase6" "observer_phase6" telephony/core/build_info.py
grep_must_exist "stt_detail in health" "stt_detail" telephony/api/http.py

log_section "L — Tone + SAFE_ACKS"
grep_must_be_empty "no внучка-ассистент" "внучка-ассистент" telephony/conversation_system/reply/prompts.py
grep_must_be_empty "no давайте дальше in SAFE_ACKS" "давайте дальше" telephony/conversation_system/reply/guards.py

log_section "M — Action Supervisor"
grep_must_exist "ActionSupervisor" "class ActionSupervisor" telephony/conversation_system/ledger/action_supervisor.py
grep_must_be_empty "no unverified delivery in pools" "уже видят\|передала близким\|оповещены\|уже могут посмотреть" telephony/conversation_system/reply/pools.py

log_section "Lua — duration loop (not hard 6-turn cap)"
grep_must_be_empty "no for i=1,6" "for i = 1, 6" telephony/moss_agent.lua
grep_must_exist "MAX_CALL_SEC" "MAX_CALL_SEC" telephony/moss_agent.lua

# --- Unit tests (targeted P0) ---
log_section "Targeted P0 unit tests"
python3 -m unittest \
  telephony.tests.test_reply_segments_stream_consumption \
  telephony.tests.test_semantic_slot_validator \
  telephony.tests.test_side_question_no_listen_reset \
  telephony.tests.test_observer_phase6 \
  telephony.tests.test_observer_phase5.GoalArbitrationTests \
  -v 2>&1 || FAIL=1

python3 -m unittest telephony.tests.test_providers.Qwen3TTSProviderTests -v 2>&1 || FAIL=1

# --- Write report ---
{
  echo "# VERIFICATION GATE REPORT"
  echo ""
  echo "Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "Root: \`$ROOT\`"
  echo ""
  for s in "${SECTIONS[@]}"; do
    echo "## $s"
    echo ""
  done
  echo "## Baseline grep (pre-fix snapshot)"
  echo ""
  echo '```'
  echo "настроении, сне или планах: $(grep -rn 'настроении, сне или планах' telephony/ 2>/dev/null | wc -l | tr -d ' ') matches"
  echo "next_directive or (session): $(grep -rn 'next_directive or' telephony/conversation_system/runtime/session.py 2>/dev/null | wc -l | tr -d ' ') matches"
  echo "for i = 1, 6 (lua): $(grep -rn 'for i = 1, 6' telephony/moss_agent.lua 2>/dev/null | wc -l | tr -d ' ') matches"
  echo "MOSS_LOCAL_ONLY refs: $(grep -rn 'MOSS_LOCAL_ONLY' telephony/ 2>/dev/null | grep -v pycache | wc -l | tr -d ' ') matches"
  echo '```'
  echo ""
  if [[ "$FAIL" -eq 0 ]]; then
    echo "**OVERALL: PASS**"
  else
    echo "**OVERALL: FAIL**"
  fi
} > "$REPORT"

echo ""
echo "Report written to $REPORT"
exit "$FAIL"
