#!/usr/bin/env bash
# Build review archives and run tests on UNPACKED copies.
# Ensures workspace PASS == archive PASS (P0-E).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="${TMPDIR:-/tmp}/mossvoice-review-${STAMP}"
GOLDEN_ARCHIVE="${WORK}/golden_path_review.zip"
PRON_ARCHIVE="${WORK}/telephony_pronunciation_review.zip"
GOLDEN_UNPACK="${WORK}/golden_unpacked"
PRON_UNPACK="${WORK}/pron_unpacked"

mkdir -p "$WORK"
cd "$REPO"

echo "[package-review] building golden_path archive..."
zip -qr "$GOLDEN_ARCHIVE" \
  golden_path \
  docs/CONVERSATION_ARCHITECTURE.md \
  scripts/run_vera_text_lab.py \
  scripts/verify_llm_readiness.py \
  scripts/stage_a_llm_gateway.py \
  Makefile

mkdir -p "$GOLDEN_UNPACK"
unzip -q "$GOLDEN_ARCHIVE" -d "$GOLDEN_UNPACK"

echo "[package-review] golden_path tests on unpacked tree..."
cd "$GOLDEN_UNPACK"
python3 -m unittest discover -s golden_path/tests -v
python3 -m unittest golden_path.tests.test_architecture_contract -v

cd "$REPO"
echo "[package-review] building telephony pronunciation archive..."
PRON_ZIP_ARGS=(
  runtime/scripts/moss_runtime/pronunciation.py
  runtime/scripts/moss_runtime/speech_frontend.py
  runtime/scripts/moss_runtime/silero_tts_backend.py
  telephony/tests/test_pronunciation_frontend.py
  telephony/adapters/moss_tts.py
  scripts/run_pronunciation_voice_gate.py
)
if [[ -d voice_gate_runs/latest ]]; then
  while IFS= read -r -d '' f; do
    PRON_ZIP_ARGS+=("$f")
  done < <(find voice_gate_runs/latest -maxdepth 1 -type f \( -name '*.wav' -o -name 'voice_gate_summary.json' \) -print0 2>/dev/null || true)
fi

zip -qr "$PRON_ARCHIVE" "${PRON_ZIP_ARGS[@]}"

mkdir -p "$PRON_UNPACK"
unzip -q "$PRON_ARCHIVE" -d "$PRON_UNPACK"

echo "[package-review] pronunciation tests on unpacked tree..."
cd "$PRON_UNPACK"
python3 telephony/tests/test_pronunciation_frontend.py -v

echo "[package-review] OK"
echo "  golden_path_archive=$GOLDEN_ARCHIVE"
echo "  pronunciation_archive=$PRON_ARCHIVE"
