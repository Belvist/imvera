"""Shared fixtures for regression tests.

The daemon/backend live in the runtime scripts dir; the tests must run under
an interpreter that hosts the audio deps (mlx_audio, soundfile, scipy, torch).

Runtime scripts are resolved in priority order:
  1. $MOSS_RUNTIME_SCRIPTS environment variable
  2. <repo>/runtime/scripts   (repo-provided runtime, no ~/Library dependency)
  3. ~/Library/Application Support/MossVoice/runtime/scripts
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_TELEPHONY = os.path.dirname(_HERE)
_REPO = os.path.dirname(_TELEPHONY)
_REPO_RUNTIME = os.path.join(_REPO, "runtime", "scripts")


def _find_runtime_scripts():
    env = os.environ.get("MOSS_RUNTIME_SCRIPTS")
    if env:
        return env
    if os.path.isdir(_REPO_RUNTIME):
        return _REPO_RUNTIME
    fallback = os.path.expanduser(
        "~/Library/Application Support/MossVoice/runtime/scripts"
    )
    return fallback


_RUNTIME_SCRIPTS = _find_runtime_scripts()

if _RUNTIME_SCRIPTS not in sys.path:
    sys.path.insert(0, _RUNTIME_SCRIPTS)
if _TELEPHONY not in sys.path:
    sys.path.insert(0, _TELEPHONY)

RUNTIME_SCRIPTS = _RUNTIME_SCRIPTS

# sample reference shipped with the app (12 s, known transcript)
SAMPLE_REF = os.path.join(_TELEPHONY, "refs", "sample.wav")
SAMPLE_REF_TEXT = (
    "Если предложение короткое, я не тороплюсь и произношу его полностью. "
    "Если предложение длинное, я делаю естественную паузу между частями."
)