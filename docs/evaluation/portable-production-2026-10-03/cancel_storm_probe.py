"""Run the exact old cancel function and current registry; no model/soak claim."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from services.inference.cancellation import CancellationRegistry

BASELINE = "75508ebf27f2c76a3eb26d23326fd1c841af0ac5"
source = subprocess.check_output(["git", "show", f"{BASELINE}:services/tts/worker.py"], text=True)
function = next(
    node
    for node in ast.parse(source).body
    if isinstance(node, ast.FunctionDef) and node.name == "cancel"
)
function.decorator_list = []
namespace = {
    "Any": Any,
    "state": SimpleNamespace(cancelled_requests=set()),
    "_cancelled": set(),
}
exec(
    compile(
        ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
        "baseline/tts/worker.py",
        "exec",
    ),
    namespace,
)
registry = CancellationRegistry()
for index in range(10000):
    payload = {"request_id": f"r-{index}", "generation_id": f"g-{index}"}
    namespace["cancel"](payload)
    registry.cancel(**payload)
result = {
    "baseline_sha": BASELINE,
    "boundary": "10000 cancel commands; exact old handler vs current registry",
    "before_retained_ids": len(namespace["_cancelled"])
    + len(namespace["state"].cancelled_requests),
    "after": registry.stats(),
    "real_model_or_capacity_benchmark": False,
}
assert result["before_retained_ids"] == 20000
assert result["after"] == {"active": 0, "tombstones": 2048}
print(json.dumps(result, indent=2))
