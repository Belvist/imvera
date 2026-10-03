# Bounded TTS production evidence (2026-10-03)

Baseline **72235946c3f5f66bb925923bc02c7f6f8540088c**, target feature/voice-zoiper-m5.
Hardware: this Linux review workspace, Python3.12; no M5/model/SIP performance claim.

## Exact before failure

`PYTHONPATH=. python docs/evaluation/tts-streaming-2026-10-03/reproduce_disconnect.py`
loads the original `_ndjson_stream` function from the pinned git object, unchanged.
A controlled producer fills its actual bounded queue. After one PCM chunk the
consumer closes: its200ms deadline expires, queue has8 items, sole executor slot
remains occupied. The probe drains its test queue afterwards to cleanly release
the baseline worker. [Record](before-disconnect.json). No production model loaded.

## After contracts

`PYTHONPATH=. python -m pytest -q tests/test_bounded_tts_streaming.py`:18 PASS.
The final two parametrized cases use actual TCP/uvicorn HTTP, HttpTTSProvider,
CallActor, PlaybackQueue and transport callback. Controlled synthesis emits the
first sentence and blocks completion of the next on an Event. The transport
receives PCM before the Event releases synthesis. Completion preserves one
canonical utterance. An interruption suppresses remaining PCM and keeps the
ledger interrupted rather than delivered. The echo-reference text list is not
delivery evidence; only the ledger owns completion.

Other cases cover disconnect during full output queue, disconnect before header
send, atomic overload response, cancellation by request ID, running-kernel
capacity retention, expiry of queued work with remote clock ignored, errors
after producer sentinel, truncated HTTP streams with no replica replay, exact
sentence text/dose/initial preservation and default-off sentence mode.

Full local source suite:3126 PASS /2 inherited genuine-LFS readiness FAIL /
9 SKIP,142.34s. It ran17 of18 final cases; additional interrupt variant separately
passes. Missing trained encoder is not substituted and readiness assertions are
not waived. Corpus500/500 PASS5.74s; policy diff12 changed/12 expected/0 unexplained.
Focused executor/provider/playback/failure selection46 PASS,5.65s. The final
`make test-dialogue-runtime` selection258 PASS,15.76s. Ruff+whitespace PASS.
Real-worker benchmark CLI help verified; no real worker available here.
Remote source CI is pending publication.

## What is not measured

No real model latency, model calls/call, first audible sound, warmth, M5 memory,
concurrent capacity, phone safety/audio or deployment. No synthetic delay is
labelled a real speed gain. [Real-worker benchmark and phone gate](../../tts-streaming-handoff.md)
provides the next measurement. Native MLX/Qwen were already streaming; this
change removes stranded work and reader-thread overhead. Sentence streaming can
reduce a batch provider's initial wait, but remains opt-in until audio QA.
