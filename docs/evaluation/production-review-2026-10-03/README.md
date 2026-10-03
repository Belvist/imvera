# Production re-review (2026-10-03)

Branch: `feature/voice-zoiper-m5`. Baseline:
`55f38a5bdfb6d1ec5ceefcf4b4779a073b79628d` (latest origin at audit start).
Baseline [CI37160316920](https://github.com/Belvist/imvera/actions/runs/37160316920)
passed, yet the fault reproductions below failed. Green source checks were not
proof of complete production failure behavior. Target M5/server/SIP endpoints
remain unavailable; this is source/controlled-I/O review, not a live incident diagnosis.

## Confirmed causes and owners

| Reproduction | First wrong decision / owner | Correction |
|---|---|---|
| Real TCP first replica stalls; CallActor's250ms cleanup expires before healthy second sees cancel | TTS adapter iterated replicas serially | TaskGroup fanout; all child requests settle on caller cancellation |
| Fresh bridge setup has no60s sweep grace | Sweep subtracts monotonic start from wall time | Monotonic elapsed time |
| Session registers while previous ESL hangup awaits | Sweep cached one live UUID snapshot | Read authoritative live registry per candidate; accept JSON list/object rows |
| Second production call reaches binding despite profile limit1 | Limit was YAML only; bridge admission owner absent | Reserve/check same registry without an await between check and reservation; finally release |
| Accept/setup failure leaves session state behind | Construction/accept were outside cleanup scope | Stop constructed actor and release admission on setup/cancellation/error |
| Lost resident still yields warm health200 | TTS readiness retained historical warmup state | Check actual model/voice metadata; fail closed; drain producers and HTTP leases before supervisor restart |
| Slowly trickling metadata exceeds probe timeout | Socket inactivity timeout mistaken for total budget | Available-packet reads, total deadline checks and64KiB body ceiling |
| Production request with no product ID accesses lab identity/manual mission path | Product resolver lacked runtime-mode guard | Reject before touching store; real product binding remains required |
| Duplex call reports active_sessions0 | Health counted only uplink registry | Count authoritative CallActor registry |

Initial five reproductions: **5 failed**, then passed after correction.
Warm-resident loss separately failed (HTTP200 instead of503). Slow metadata
reproduction failed to time out. Missing product identity (two cases) and active
session count separately failed. Expectations were retained; no existing test
was removed, weakened or skipped.

## Verification and limits

`tests/test_production_review_boundaries.py` verifies the faults plus concurrent
setup/cleanup, failed accept, model-change refusal, voice-registry loss, actual
subprocess exit70 and draining the HTTP consumer after producer completion.
It joins `make test-dialogue-runtime` and the full suite.

Production-workers CI additionally runs the actual unprivileged/read-only TTS
container with controlled PCM. It first streams/cancels, takes the resident
offline **after warm readiness**, observes503, waits for supervisor restart,
restores the resident and proves same-model readiness plus another complete
stream. `worker-recovery.json` is uploaded by CI. This fixture is explicitly not
a neural voice, phone recording, human-dialogue evaluation or capacity test.

Exact final commands/counts and source/CI are recorded in `docs/current-task.md`
after gates complete. No load/genuine TTS/SIP acceptance is inferred from them.

The active DialogueEngine/Reducer/renderer/playback ledger and canonical text
are unchanged. No neural generator or template bank was enabled or extended.
Health probes make no synthesis calls; normal synthesis retains its existing
model call count. This review adds fault coverage, not a claim that dialogue
became more human. Accepted resident artifacts, Core/PG/consent, audible
interruption/latency, real dialogue recordings and target soak remain the next gate.
