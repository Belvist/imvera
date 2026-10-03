import ast
import asyncio
import json
import queue
import subprocess
import threading
from collections.abc import AsyncIterator
from pathlib import Path

from services.inference import common
from services.inference.common import (
    InferenceExecutor,
)
from services.tts.worker import SynthesizeRequest

source = subprocess.check_output(
    ["git", "show", "72235946c3f5f66bb925923bc02c7f6f8540088c:services/tts/worker.py"], text=True
)
node = next(
    n
    for n in ast.parse(source).body
    if isinstance(n, ast.AsyncFunctionDef) and n.name == "_ndjson_stream"
)
stop = threading.Event()
full = threading.Event()
queues = []
executor = InferenceExecutor(max_queue=1)


def produce(req, output):
    queues.append(output)
    while not stop.is_set():
        if output.full():
            full.set()
        output.put({"pcm_b64": "AQABAA==", "sample_rate": 16000})
    output.put(None)


namespace = dict(
    globals(),
    _produce_chunks=produce,
    _cancelled=set(),
    AsyncIterator=AsyncIterator,
    check_deadline=common.check_deadline,
    QueueFullError=common.QueueFullError,
    executor_http_error=common.executor_http_error,
)
exec(
    compile(ast.Module(body=[node], type_ignores=[]), "<exact-original-stream>", "exec"), namespace
)


async def run():
    iterator = namespace["_ndjson_stream"](
        SynthesizeRequest(call_id="probe", generation_id="g", phrase_id="p", text="Поняла.")
    )
    await anext(iterator)
    async with asyncio.timeout(1):
        while not full.is_set():
            await asyncio.sleep(0.005)
    timed_out = False
    try:
        await asyncio.wait_for(iterator.aclose(), timeout=0.2)
    except TimeoutError:
        timed_out = True
    record = {
        "source_sha": "72235946c3f5f66bb925923bc02c7f6f8540088c",
        "boundary": "exact original worker _ndjson_stream; controlled producer, no real model",
        "consumer_close_timeout_200ms": timed_out,
        "executor_pending_after_disconnect": executor.queue_depth,
        "queue_items": queues[0].qsize(),
        "result": "FAIL: disconnected consumer strands sole worker"
        if timed_out and executor.queue_depth == 1
        else "unexpected",
    }
    stop.set()
    async with asyncio.timeout(2):
        while executor.queue_depth:
            while True:
                try:
                    queues[0].get_nowait()
                except queue.Empty:
                    break
            await asyncio.sleep(0.005)
    Path("docs/evaluation/tts-streaming-2026-10-03/before-disconnect.json").write_text(
        json.dumps(record, indent=2) + "\n"
    )
    print(json.dumps(record))


asyncio.run(run())
executor._executor.shutdown()
