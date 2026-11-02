"""Isolated genuine warmed polarity cost; not phone or full SDK latency."""

import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("checkout", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
root = args.checkout.resolve()
sys.path.insert(0, str(root))

from packages.dialogue_engine.semantic_kernel.observation_memory import (  # noqa: E402
    _polarity_model_vote,
)
from packages.dialogue_engine.semantic_nlp.polarity import PolarityModel  # noqa: E402

model = PolarityModel.get()
model.predict("Спасибо, хорошо.")
original = model.predict
calls = []


def counted(text):
    calls.append(len(text))
    return original(text)


model.predict = counted
text = "Спала плохо. " + "Вчера гуляла с дочерью в парке. " * 30
timings, votes = [], []
for _ in range(3):
    started = time.perf_counter()
    votes.append(_polarity_model_vote(text))
    timings.append((time.perf_counter() - started) * 1000)

args.output.write_text(json.dumps({
    "scope": "isolated warmed optional polarity helper; no SDK/STT/TTS/SIP",
    "platform": platform.platform(), "logical_cpus": os.cpu_count(),
    "cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
    "input_chars": len(text), "predict_calls": len(calls),
    "samples_ms": timings, "median_ms": statistics.median(timings), "votes": votes,
    "source_sha256": hashlib.sha256((root / "packages/dialogue_engine/semantic_kernel/"
                                     "observation_memory.py").read_bytes()).hexdigest(),
}, ensure_ascii=False, indent=2) + "\n")
