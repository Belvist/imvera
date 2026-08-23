"""Runtime-scripts path resolution shared by the telephony modules.

The runtime dir hosts tts_common/backends. Both call_agent and the tests
insert it into sys.path so ``import tts_common`` works regardless of the
deployment layout (repo checkout, installed app, Docker).
"""

import os
import sys


def runtime_scripts_dir():
    """Resolve the runtime scripts dir hosting tts_common/backends.

    Priority: $MOSS_RUNTIME_SCRIPTS -> <repo>/runtime/scripts -> the installed
    app runtime (~/Library/...). Keeps the agent operable from the repository
    without depending on a machine-specific home path.
    """
    env = os.environ.get("MOSS_RUNTIME_SCRIPTS")
    if env:
        return env
    _here = os.path.dirname(os.path.abspath(__file__))
    _repo_runtime = os.path.join(os.path.dirname(_here), "runtime", "scripts")
    if os.path.isdir(_repo_runtime):
        return _repo_runtime
    support = os.path.expanduser("~/Library/Application Support/MossVoice")
    return os.path.join(support, "runtime", "scripts")


def ensure_runtime_scripts():
    """Insert the runtime scripts dir at sys.path[0] if not already there."""
    p = runtime_scripts_dir()
    if p and p not in sys.path:
        sys.path.insert(0, p)