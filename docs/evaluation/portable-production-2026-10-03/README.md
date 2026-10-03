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

Actual source gates, Linux image IDs/build/dependency/failed-boot/controlled-HTTP
container results and exact source CI are recorded below.
Actual target hardware models, SIP audio and capacity are **NOT VERIFIED**.

## Actual final source checks

Final launch source: `f7fbc89270ffeb67e41234b8c22e6fd4d789a08c`.
Actual model/container source: `2e78b543d3ccd5854d44eb681f1f07b8d016b06c`.
Git comparison proves packages/services/config/pyproject/Dockerfiles/tests/Makefile
byte-identical between these revisions. Final source additionally requires the
accepted offline HF cache and bounds bridge resources in the Compose overlay.
[Machine-readable checks](checks.json) preserve failures as well as successes.

| Command / boundary | Actual result |
|---|---|
| `make test-dialogue-runtime` | 298 passed,17.53s (candidate65c028f; subsequent exact CI reruns same contracts) |
| Production/HTTP/bounded-stream focused tests | 58 passed,3.77s |
| Offline artifact correction selection | 43 passed,1.11s |
| Full local suite, `OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2` | 3167 passed /2 inherited missing genuine relation-LFS failures /9 skipped,153.94s; **NOT locally green** |
| Previous local full suite, host defaults | 3166 passed /3 failed /9 skipped,159.17s; third failure is polarity candidate=None (exact rejection reason not instrumented) |
| Same isolated polarity tests, default vs2 library threads | 1 pass/2 failures,17s →3 passes/0 failures,6.05s; original300ms production budget and model/code untouched |
| Final-source corpus | 500/500 PASS,5.74s |
| Final-source frozen policy differential | 12 changed /12 expected /0 unexplained PASS |
| `ruff check packages services tests scripts` + evidence scripts + whitespace | PASS |
| Merged production `docker compose … config --quiet` | exit0; explicit placeholder paths/endpoints only, no deployment |

The local relation encoder remains an actual LFS pointer; its deserializer fails
readiness. Genuine CI LFS hydration remains mandatory. No substitute weights,
readiness waiver or reduced expectations were used. A later idle
[direct classifier probe](cpu-thread-probe.json) passed with both defaults
(3 threads,94–108ms) and2 threads (64–66ms). The earlier failed run was not
instrumented for exact reject reason; thread caps alone do not prove load
capacity or guaranteed300ms. Exact CI record follows in
[ci.json](ci.json). Source2e78b54 [run37158803714](https://github.com/Belvist/imvera/actions/runs/37158803714)
already passed all11 jobs, including private-source container builds and full
3175 tests/0 failures/3 skipped,184.71s. Final launch-source [run37159569169](https://github.com/Belvist/imvera/actions/runs/37159569169)
passed all11 jobs,3175/0/3 in224.09s; exact runtime298 passed,20.11s.
Production-workers gate includes offline-cache Compose validation and both image
builds plus unprivileged dependency/failed-selected-voice checks.

## Actual Linux containers and faults

Linux **x86_64** Docker28.4.0; immutable Python base digest in the handoff.
TTS image `sha256:953a45b8b5f7712ea64640ed382df2b8ab54d370672b5492ceb210c606c9016d`;
STT image `sha256:e166562ee8209a4672ef7c9e07fd55b22562cba793a3a1460c12f44354ddc659`;
both UID10001, revision2e78b54. CPU Torch/TorchAudio2.11.0 wheels and GigaAM
7447938d791c4f3e643386ee22c33777004293a5. Build logs confirmed pinned dependencies;
actual prior-image dependency probe reported2.11.0+cpu, no CUDA, two torch threads,
and working ffmpeg. Actual final STT model warmup/transcription exercises them.

[container_probe.py](container_probe.py), [result](container.json): real hardened
Docker TTS worker, synthetic PCM resident fixture in a shared loopback network
namespace (managed Docker proxy routing retained). Worker ready SHA/profile/model
identity; four frames with complete marker; explicit generation cancellation;
actual pending count/active leases return0. Normal stop0.232s. Failed resident
startup causes supervisor restart (RestartCount≥1) and no Silero. This proves
lifecycle/HTTP/resource configuration; **62ms fixture first frame is not neural
TTS latency**. Compose service DNS/proxy routing must be verified on target.

Build/probe failures drove fixes, not weakened acceptance:

- First STT image build could not obtain TorchAudio2.14.1; pin a genuinely
  available matching CPU pair2.11.0/2.11.0 and make image builds mandatory in CI.
- Private checkout mode700/600 made imports inaccessible to UID10001. COPY now
  assigns that UID; CI deliberately uses private permissions before building.
- Actual managed Docker proxy cannot resolve fixture service names externally;
  local shared namespace isolates the fixture without changing proxy policy.
- Managed daemon uses VFS and exhausted the small review disk during repeated
  image copies. Only this task's temporary containers/failed images/build-cache
  records were removed; prior images/database volumes were preserved. Accepted
  images remain. This is not target-server capacity evidence.

## Actual neural STT, not a mock

Official [GigaAM artifacts/checksums](gigaam-artifacts.json) were downloaded in a
separate preparation step and mounted read-only. Checkpoint448929252 bytes matches
upstream MD5; tokenizer255336 bytes, both SHA256 recorded. No runtime download.
Actual production Linux GigaAM worker with two-core quota/4GiB cap accepted four
repository mono PCM WAVs over HTTP; [full outputs](real-stt.json):

| WAV | Actual recognized text | HTTP processing latency |
|---|---|---|
| wellness_bad_03 | Сегодня плохо. | 312.76ms |
| decline_nothing_hurts_01 | Ничего не болит, всё хорошо. | 354.77ms |
| mood_positive_01 | Настроение хорошее. | 349.44ms |
| plans_walk_01 | Пойду гулять. | 329.62ms |

Four short1.04–1.95s clips only; p50339.53ms, nearest-rank p95354.77ms (=maximum
of four samples). These are warm HTTP STT processing times, not end-of-speech→PCM,
phone latency, general ASR accuracy or concurrent capacity. Actual idle memory
measurement after these calls:1.707GiB/4GiB,12 PIDs, no OOM. All outputs GOOD under
the existing quality rules; no ASR quality was fabricated by the test.
[stt_http_probe.py](stt_http_probe.py) is the reusable form of the executed probe.

Stop satisfied the <30s assertion; Uvicorn logged complete application shutdown
and propagated SIGTERM, exit143 (not OOM/forced SIGKILL137). The initial helper
incorrectly expected exit0 and failed *after* the duration assertion; exact stop
duration was not persisted. Signal code/log validation is recorded explicitly in
JSON. Temporary model/fixture containers were removed; no live services touched.

## Outstanding acceptance

Actual accepted resident Qwen model/voice on selected target hardware, M5 or server
rollout, full CallActor/FreeSWITCH phone recording, end-of-speech/first-audible
latency, interruption/soak, Core/consent/PG and throughput remain **NOT VERIFIED**.
Model artifacts and supervisor/routing must be matched before launch. No claims
of zero failure risk,100 simultaneous calls, a million users or human warmth are
made from these measurements. Next gate is real target model/SIP/audio acceptance.
