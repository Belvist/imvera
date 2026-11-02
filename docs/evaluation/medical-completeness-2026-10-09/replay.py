"""Reuse the existing evidence harness with identical medical correction cases."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
shared = ROOT / "docs/evaluation/grounded-coverage-2026-10-07/replay.py"
spec = importlib.util.spec_from_file_location("coverage_capture", shared)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.CASES = {
    "three_food_medication": ["Мне хорошо. Сегодня поела, таблетки уже приняла."],
    "three_mood_sleep": ["Мне хорошо. Настроение хорошее. Выспалась."],
    "all_five": ["Мне хорошо. Сегодня поела. Таблетки не принимаю. Настроение хорошее. Выспалась."],
    "separate_five": ["Хорошо.", "Поела.", "Нет.", "Нормальное.", "Выспалась."],
    "unavailable_food": ["Хорошо.", "Не помню.", "Нет.", "Нормальное.", "Выспалась."],
    "refused_food": ["Хорошо.", "Не хочу отвечать.", "Нет.", "Нормальное.", "Выспалась."],
    "story_resume": ["Мне хорошо. Сегодня поела, таблетки уже приняла.",
                     "Вчера дочь приехала, мы смотрели фотографии.", "Нет, больше ничего."],
    "urgent": ["Хорошо.", "Мне сейчас трудно дышать."],
    "stop": ["Хорошо.", "До свидания."],
}
module.main()
output = Path(sys.argv[1])
data = json.loads(output.read_text())
root = Path(sys.argv[sys.argv.index("--checkout") + 1]) if "--checkout" in sys.argv else ROOT
for name in ("packages/dialogue_engine/topic_tracker.py", "packages/dialogue_engine/reducer.py"):
    data["source_hashes"][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
