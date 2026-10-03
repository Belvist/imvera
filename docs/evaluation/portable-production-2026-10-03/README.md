# Portable production inference evidence (2026-10-03)

Baseline `75508ebf27f2c76a3eb26d23326fd1c841af0ac5`, target `feature/voice-zoiper-m5`.
Source audit and launch contract: [ADR-031](../../adr/031-portable-production-inference.md),
[operator handoff](../../production-server-handoff.md).

## Reproduction and scope

`PYTHONPATH=. python docs/evaluation/portable-production-2026-10-03/cancel_storm_probe.py`
executes the exact old cancel function AST against its original set-shaped owners
and the new sole cancellation registry. [Result](cancel-storm.json):10000 cancel
commands retain20000 old IDs versus2048 new tombstones/0 active leases. This is a
memory-retention boundary proof, not a real-model or multi-million-user benchmark.

`tests/test_production_inference.py` proves cancellation survives tombstone
expiry/eviction for active requests, duplicate identities/overload, bounded bytes
and active streams, stalled ASGI sends, source/profile/backend validation,
production fallback rejection, offline artifact failure, real executor capacity
through shutdown and real process exit70 for hung job/startup.

`tests/test_qwen_http_streaming.py` uses an actual loopback HTTP server and the
native Qwen client: first16 PCM bytes arrive before later packets are released,
cancel prevents the next packet read, and a stalled socket obeys a short timeout.
These controlled packets are not a neural voice or hardware benchmark.

`tests/test_bounded_tts_streaming.py` retains TCP/provider/CallActor/transport and
interrupted playback-ledger assertions. Canonical speech, safety/state owners,
model choice and production dialogue policy are unchanged.

Source gates, actual Linux image IDs/build/dependency/failed-boot/controlled-HTTP
container results and exact source CI will be added to this report after running.
Actual target hardware models, SIP audio and capacity are **NOT VERIFIED**.
