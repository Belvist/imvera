#!/bin/zsh
# Regression tests (P0-VC-002/003/004).
#
# The venv hosting the audio deps (mlx_audio, soundfile, scipy, torch...) is
# located here, in priority order:
#   1. MOSS_PY environment variable
#   2. ./runtime/qwen-venv/bin/python   (repo-provided runtime)
#   3. ~/Library/Application Support/MossVoice/runtime/qwen-venv/bin/python
set -e
TEL="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(dirname "$TEL")"
if [ -n "${MOSS_PY:-}" ]; then
    PY="$MOSS_PY"
elif [ -x "$REPO/runtime/qwen-venv/bin/python" ]; then
    PY="$REPO/runtime/qwen-venv/bin/python"
else
    PY="$HOME/Library/Application Support/MossVoice/runtime/qwen-venv/bin/python"
fi
cd "$TEL"
exec "$PY" -m unittest discover -s tests -v "$@"