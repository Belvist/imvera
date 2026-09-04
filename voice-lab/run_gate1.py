"""Gate 1 harness — DEPRECATED (legacy Agent removed 2026-09-03).

Use instead:
    python3 voice-lab/dialog_quality.py --strict
"""

import sys


def main() -> int:
    print(__doc__)
    print("\nLegacy core.dialogue.Agent was removed.")
    print("Run: python3 voice-lab/dialog_quality.py --strict")
    return 2


if __name__ == "__main__":
    sys.exit(main())
