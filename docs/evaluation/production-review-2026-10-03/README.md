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

The follow-up reproduced one admission gap in the initial fix: a channel waiting
for provider readiness was not yet reserved. Reservation now precedes that await;
concurrent attempts reject immediately and caller cancellation releases the slot.

Initial container CI37162506889 observed warm readiness, stream/cancel,503 after
resident loss, supervisor restart, recovered same-model readiness and another
complete stream. The job then failed its log assertion because Docker's stderr
(where the watchdog logs) was printed but not captured by the collector. The
collector now captures both log streams; the assertion remains. Final gate passes.

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

Final source **3ae3ea87465b5eb561fee716f1784610883c9343**:
[CI37162766797](https://github.com/Belvist/imvera/actions/runs/37162766797)
**11/11 jobs PASS**, full3193 passed/0 failed/3 skipped,223.61s;
runtime316 passed,23.15s. The18 new fault cases join the original expectations.
Final local runtime316 PASS,20.17s. Local full before the final HTTP-drain
correction3184 PASS/2 inherited genuine-LFS readiness failures/9 skipped,
147.03s; not locally green. Final CI has genuine hydrated artifacts.
[Machine-readable checks](checks.json) preserve the failed first container gate.

[Verified container artifact](container.json), official ZIP artifact11288267761,
SHA256 `f87c2407684256faa60107253ead06106e3e770fdf8605c9a0e339a2b1a96bbd`.
Actual image `sha256:15b63ff74236d68426552c88a4c0bbd29fd88c032ea8f3a881c657408910522f`;
source/profile metadata verified; normal stop0.238s, warm and cold supervisor
restarts, four frames in each completed stream, settled active/queue0, same
model, no fallback. Controlled first-frame30.95ms is not neural TTS latency.
No load/genuine TTS/SIP acceptance is inferred from these results.

The active DialogueEngine/Reducer/renderer/playback ledger and canonical text
are unchanged. No neural generator or template bank was enabled or extended.
Health probes make no synthesis calls; normal synthesis retains its existing
model call count. This review adds fault coverage, not a claim that dialogue
became more human. Accepted resident artifacts, Core/PG/consent, audible
interruption/latency, real dialogue recordings and target soak remain the next gate.
