"""Reuse the paired SDK recorder for whole vs mixed listening completion."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def main():
    path = Path(__file__).resolve().parent.parent / "continuation-2026-10-07" / "replay.py"
    spec = importlib.util.spec_from_file_location("continuation_capture", path)
    recorder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recorder)
    recorder.CASES = {
        "whole_no_more": (1, recorder.ROUTINE + recorder.STORY[:2]
                          + ["Нет, ничего.", "До свидания."]),
        "whole_soft_no": (1, recorder.ROUTINE + recorder.STORY[:2]
                          + ["Вроде бы нет.", "До свидания."]),
        "whole_nothing_else": (1, recorder.ROUTINE + recorder.STORY[:2]
                              + ["Больше ничего.", "До свидания."]),
        "mixed_continuation": (1, recorder.ROUTINE + recorder.STORY[:2]
                               + ["Вроде нет, а потом мы вспоминали нашу поездку к морю.",
                                  "На этом всё.", "До свидания."]),
        "resume_required_wellness": (1, ["Внучка приезжала, хорошо посидели.",
                                       "Вспоминали нашу поездку к морю.",
                                       "Нет, ничего.", "Самочувствие хорошее."]),
    }
    recorder.main()


if __name__ == "__main__":
    main()
