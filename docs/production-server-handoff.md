# Portable production workers: operator handoff (2026-10-03)

Target branch: `feature/voice-zoiper-m5`. Source baseline: `75508eb`.
[ADR-031](adr/031-portable-production-inference.md) owns this change;
[current-task](current-task.md) records exact tested/published revisions.
This is a server launch contract, not a claim of an accepted deployment.

The [2026-10-03 re-review](evaluation/production-review-2026-10-03/README.md)
corrects the first launch's admission claim: the profile contained a one-call
limit, but the bridge did not enforce it. Production now reserves a slot before
setup, rejects excess sessions with WS1013, and releases it on every exit,
including failed construction/accept. The limit is **per bridge process**;
do not run multiple ASGI workers to multiply admission implicitly. Production
connections require `call_id` / `imvera_call_id` and a real shared CallBinding;
no manual `mission` or lab family fallback is allowed. Health counts this same
registry, including setups/closing sessions.

## One codebase, explicit backend

The bridge, DialogueEngine/Reducer, CallActor, provider contracts, streaming and
cancellation remain the same on Mac and Linux. Use an explicit
`IMVERA_VOICE_PROFILE_PATH` for **all** processes. The M5 can keep its accepted
profile/backend; Linux must not select Apple MLX. Workers now use the bridge's
existing profile resolver rather than silently reading `voice-m5.yaml`.

`config/voice-linux-cpu.yaml` uses existing CPU GigaAM and the existing Qwen
resident HTTP/PCM protocol. It does not install a new voice or model server.
Provision the accepted voice's resident server separately, pin its executable
and model/license/checksums, and supply `IMVERA_QWEN_TTS_URL`. Its Linux CPU/GPU
implementation and capacity must be measured on the selected server. The Python
TTS worker image contains the client, not the neural speech model. Do not deploy
an unaccepted voice implementation just to satisfy health checks.

## Build and launch

Use the **same full commit** for bridge and worker images. In a clean checkout,
set `IMVERA_GIT_SHA` to `git rev-parse HEAD`, and `IMVERA_PYTHON_IMAGE` to a pinned
Python image digest. The reviewed base is
`python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3`.

Supply these configuration values through the deployment's secret/configuration
system; never commit database credentials:

- `IMVERA_PG_URL`: real production PG with required migrations and Core handoff.
- `IMVERA_NLP_MODELS_DIR`: genuine accepted act/relation/polarity/head artifacts;
  Git LFS pointers are not weights.
- `IMVERA_HF_CACHE_DIR`: prepared accepted RuModernBERT encoder/tokenizer
  Hugging Face home (includes `hub/` snapshots and pinned refs). Bridge mounts it
  read-only and sets HF/Transformers offline mode; no live download of an
  unreviewed encoder revision. Verify snapshot revision/checksums with the heads.
- `IMVERA_GIGAAM_MODELS_DIR`: prepared `v3_e2e_rnnt.ckpt` plus
  `v3_e2e_rnnt_tokenizer.model`; worker checks upstream checkpoint checksum.
- `IMVERA_QWEN_TTS_URL`: reachable accepted resident server (HTTP/S, no embedded credentials).
- `IMVERA_VOICE_ARTIFACTS_DIR`: accepted `vera_kseniya.spk`, `.rvq`, `_ref.txt`
  when the resident voice registry needs registration after restart.
- `IMVERA_FS_IMAGE_TAG`: the accepted FreeSWITCH image, not a surprise rebuild.

Compose overlay merges the existing bridge, without a second bridge/scheduler:

```sh
docker compose -f infra/freeswitch/docker-compose.yml \
  -f infra/inference/compose.production.yml config --quiet
docker compose -f infra/freeswitch/docker-compose.yml \
  -f infra/inference/compose.production.yml build media-bridge stt-worker tts-worker
docker compose -f infra/freeswitch/docker-compose.yml \
  -f infra/inference/compose.production.yml up -d stt-worker tts-worker media-bridge freeswitch
```

For builds behind a trusted proxy, pass the environment's CA using the existing
BuildKit secret `proxy_ca`; never disable TLS verification. Model preparation is
a separate controlled operation; production STT defaults to offline artifacts.
Use entrypoints `python -m services.stt.worker` / `python -m services.tts.worker`:
TTS main-thread warmup must finish before the HTTP server binds.
Model mounts must be readable by worker UID10001. Prepare permissions for the
public model artifacts explicitly; do not relax database/recording permissions.

## Bounds and failure behavior

Production mode requires explicit source/profile, known platform/backend and
finite queue/turn/process limits. Linux profile initially admits one call, with
four pending inference jobs **including** the running one, one model thread per
worker, STT12s/TTS20s call budgets, job120s/startup240s hard process bounds.
Multiple calls are async; HTTP/playback overlap synthesis. Replicate workers only
after measuring accepted model throughput; extra threads do not create neural
compute capacity. No large LLM is enabled by this deployment.
Bridge defaults to4GiB/two CPU cores and two OMP/BLAS threads; inference workers
also cap library threads. Align thread counts with measured CPU quotas. A concurrent
review run had polarity candidate-abstention failures; two-thread isolated tests
passed without raising the300ms budget. Later idle probes passed with both
default3 threads (94–108ms) and2 threads (64–66ms). Thread caps bound resource use;
target load/capacity still needs measurement.

Keep each active CallActor/EngineState on one bridge process. Scale the existing
STT/TTS replica pool with explicit reachable worker URLs: cancellation broadcasts
to the configured replicas and failover is allowed only before first PCM.
TTS cancellation is concurrent across replicas and drains its child requests
when CallActor cancels the cleanup; a hung first replica cannot prevent the
playing replica from receiving cancellation.

Production Qwen readiness rechecks the warmed model identity and accepted voice
registration, without synthesizing speech. Metadata reads are bounded by time
and64KiB. Lost resident/registry revokes admission immediately when observed;
the existing model-process watchdog drains admitted producers **and HTTP leases**
before exit70 (hard recovery bound remains the configured job timeout).
`restart: unless-stopped` then repeats the existing bootstrap and voice
registration/warmup. New readiness requests must pass before admitting calls.
Model identity change instead returns503 for operator review and does not
automatically accept a new model. Pin the resident executable/model/artifacts
as described above; an intentional process restart reruns bootstrap, so the
deployment's accepted artifact identity remains an operator contract.

The bridge orphan sweep honours60s monotonic startup grace and consults current
live sessions before each hangup. Reconnect/resume of the same channel remains
unsupported; a new channel is required. None of these checks proves an audible
stop or a warm, natural dialogue: retain the real audio/trace acceptance gate.
An opaque load-balancer URL is not proof that cancellation reaches every worker.
Check private service DNS/routing and configured proxies on the deployment host.

Workers have private Docker networking, unprivileged UID10001, read-only root,
bounded writable tmpfs/memory/CPU/PIDs and30s container shutdown budget.
Readiness reports real source SHA/profile digest/model revision and queue depth;
TTS also exposes cancellation active/tombstone counts. A selected voice failure
in production remains a failure, never lab Silero. Startup failure or model job
exceeding its hard bound exits the dedicated worker process70; restart policy
restarts it. Ordinary saturation returns429 before streaming headers. Container
stop cancels queued work; executing kernels retain their slot until they return
or their process is terminated. This guard never kills the SDK/state writer.

TTS cancellation keeps active Events until producer **and** HTTP consumer settle;
unknown/early/late IDs expire after120s with at most2048 tombstones.
At most32 HTTP streams remain active, including completed producers with slow
consumers; the request deadline also covers stalled ASGI socket writes. Output queue
has both8-chunk and2MiB encoded-payload bounds. ID length≤160, finite deadlines
and duplicate-live-ID rejection prevent ambiguous unbounded request state.
Qwen yields available PCM without waiting to fill a0.4s read buffer, checks
cancel/deadline between packets, and closes HTTP resources. A currently blocked
read cannot be preempted instantly; socket/process bounds contain it. Partial
speech failure cannot replay a different voice or count as heard completion.

## Acceptance / rollback

First verify matching deployed SHA/profile/model IDs and genuine readiness;
then record actual CallActor/FreeSWITCH audio/trace, end-of-speech→firstPCM and
first audible sound p50/p95, interruption, overload/restart/soak and Core outcomes.
Run existing live-call gates before increasing admission. Store model calls/turn,
RAM and CPU/GPU utilization with accepted concurrent count. Synthetic HTTP and
container failure gates prove lifecycle/contracts, not voice quality/capacity.

Rollback uses the previously accepted source **and its matching profile/images,
model artifacts and resident endpoint**; preserve database/consent/recordings.
Do not substitute another backend to make readiness green. No services on the
M5 or a target server were restarted by this source change.

## Published verification

Launch source `f7fbc89270ffeb67e41234b8c22e6fd4d789a08c`: [CI37159569169](https://github.com/Belvist/imvera/actions/runs/37159569169)
all11 jobs PASS,3175 tests/0 failures/3 skipped. [Recorded image/model evidence](evaluation/portable-production-2026-10-03/README.md)
uses runtime-identical source2e78b54: genuine CPU GigaAM4 WAVs,313–355ms HTTP
processing, and actual Docker TTS lifecycle with controlled PCM (not neural TTS).
Server deployment/SIP/neural voice/load still NOT VERIFIED. Build the documented
launch source to preserve matching image/runtime SHA; final docs-only commits do
not require changing the accepted worker/model artifacts.
