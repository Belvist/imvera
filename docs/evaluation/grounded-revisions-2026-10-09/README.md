# Grounded revisions / dispositions: source evidence, 2026-10-09

Target `feature/voice-zoiper-m5`; baseline
`c1b3f1a35d41b78fd0ee7109ddbbe6efc0df04de`. These are source/SDK checks,
not target phone acceptance. Captures label the working source **dirty** and
record SHA256 of all 21 relevant modules; HEAD alone does not identify those
bytes. `verify.py` checks the current files against the captured bytes.
Exact published source **4274a45149c46b2141cb5fe2d3e2dfce37b90cdc** passed
[CI37979468470](https://github.com/Belvist/imvera/actions/runs/37979468470):
**11/11 SUCCESS, 3647 PASS / 0 FAIL / 3 SKIP**, 237.28s; actual LFS fetch
observed. [Machine-readable receipt](source-ci.json). The following metadata-only
pin freezes those same ten v11 core files; it does not promote medical authority
or claim deployment/audio acceptance.

## What changed, with existing owners

| Failure before | Result after | Owner |
|---|---|---|
| Positive sleep survived «я перепутала, спала плохо»; old summary/goodbye won | Current source-admitted revision and later waking detail retained; old summary invalidated | Understand → existing Reducer fact writer → topic/policy |
| Another complaint's «пять часов» could replace sleep | Explicit sleep report separated from contextual bare quantity; medical/activity clocks are not sleep | Existing fast matcher/extractor and mission projection |
| Policy asked onset again after «не помню»; local refusal repeated too | Unknown/refusal discharged, never inserted as known onset | Existing unavailable-answer writer + v11 legal set |
| «голова болит… сейчас ещё болит, терпимо» created a second unsited episode | One anatomical owner retains onset/current/degree | Existing kernel relations and original span projection |
| Functional question was a generic complaint invitation with no answer writer | Ordinary-activity question accepts current caller activity or heard literal yes/no | Existing product renderer + issue memory |
| Long poor-sleep narration exceeded typed value limit | Bounded original sleep fragment; whole input still understood, including later complaints | Existing extractor/adjudication |
| Urgent speech promised unconfirmed notification | Direct close-contact/112 guidance; urgent signal unchanged | Existing canonical urgent renderer |
| Demo could show GREEN on failed call, leak token-bearing errors, or mark partial delivery sent | Truthful display, sanitized errors, locked atomic per-recipient acceptance/retry | Existing demo reporter; mocked transport only |

All five baseline medical topics remain required in opt-in full check-in. No
live generator, second state writer/FSM/selector, new model or global medical
policy cutover. v9/v10 manifests remain immutable; v11 source is now pinned after
observed exact-source CI. No behavior/test/gate bytes changed for that receipt.

## Actually run

- Full genuine-model local suite on the final dialogue code:
  `python -m pytest tests/ -q`: **3636 passed / 0 failed / 9 skipped**, 180.20s.
  Later demo retry tests are separately **12/12**, 0.09s; exact published CI
  must cover that final combined tree.
- `make test-dialogue-rich`: **1038/1038**, 15.33s.
- `make test-dialogue-runtime`: **338/338**, 22.46s; controlled audio/fake
  provider/network fault checks are not a target M5/SIP call.
- Topic **68/68**, kernel **294/294**, shadow **84/84**.
- `make dialogue-corpus-gate`: **500/500**, 6.20s + **8/8** gate tests.
- `policy_diff_v8_v9.py --comparison v9-current`: **12 expected differences,
  0 unexplained**, whole ten-file isolation/restoration. This historical
  differential does not substitute for the new disposition SDK tests.
- New public SDK/ownership tests include revisions, historical/foreign/conditional
  negatives, repeated source positions, unavailable answers, ordinary activity,
  cancelled functional question, and long speech with complaints beyond char500.
- `verify.py`: **38/38** capture/source invariants, including legacy/shadow
  spoken parity and lack of fabricated temporal values.
- Ruff, contracts import gate and `git diff --check`: PASS.

Root causes were reproduced before fixes. Initial revisions:4 FAIL/10 PASS;
clinical continuation:2 FAIL; repeated quote offsets:3 FAIL;
long sleep:3 FAIL; local refusal:1 FAIL; literal functional yes/no:2 FAIL;
default SDK sleep overwritten by headache:2 FAIL. The identical first eleven
demo tests on detached baseline:7 FAIL/4 PASS; corrected reporter:11 PASS,
then one additional real watcher/poll test:12 PASS. No real message sent.

## Actual SDK captures

`replay.py` runs 15 scenarios, 32 attempted turns per mode and side. Baseline
has one `ValidationError` in the long sleep case; final source has none.
Speech delivery is explicitly simulated with `on_playout_completed`.
All three real semantic models warm successfully before timing starts.
Generative paths are disabled; ordinary medical cutover is enabled only in
the isolated `policy` replay, not deployed.

| Final SDK mode | p50 ms | p95 ms | Success / attempts |
|---|---:|---:|---:|
| legacy | 4.39 | 12.44 | 32/32 |
| shadow | 3.59 | 9.07 | 32/32 |
| policy | 3.77 | 12.61 | 32/32 |

These are **SDK-only Linux container timings**, cgroup2 CPU, not
end-of-speech→PCM, M5 latency, throughput or a 100-call result. The three
instrumented semantic methods have **0 post-warm calls in this supported
SDK cohort**; this excludes inference performed by CallActor/provider stages.
It does not establish zero model calls in a real call. No generative call was
introduced. Baseline metrics exclude its failing turn; do not claim a universal
before/after latency improvement from unequal successful populations.

The separate `polarity_probe.py` exercises the real warmed optional whole-text
helper on the same 973-character narration: before **3 predict calls**, median
392.95ms, all votes discarded; after **0 predict calls**, early abstention.
Three samples are a root-cause check, not a production percentile. Original
literal evidence and all medical/safety processing remain available.

Reproduction (venv with genuine prepared artifacts; offline cache required):

```bash
python docs/evaluation/grounded-revisions-2026-10-09/replay.py /tmp/after.json --mode policy --warm-models
python docs/evaluation/grounded-revisions-2026-10-09/replay.py /tmp/before.json --checkout /path/to/c1b3f1a --mode policy --warm-models
python docs/evaluation/grounded-revisions-2026-10-09/verify.py
python docs/evaluation/grounded-revisions-2026-10-09/polarity_probe.py /path/to/checkout /tmp/polarity.json
```

Use `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`, as captured. The checked-in
six JSON captures, polarity probes and policy differential are actual outputs,
not invented illustrative transcripts. Recreating different source invalidates
the exact byte check until captures are regenerated.

## Not verified / remaining gates

No configured M5/Core target identity, credentials or VPN route in this session.
No deployment/restart, new FreeSWITCH call, real STT recognition comparison,
first audible PCM, barge-in stop, human warmth/listening or family/Core receipt.
Production admission remains1. HTTP routing and SDK tests are not100 full calls.
Free speech still uses deterministic supported meanings; universal human-like
conversation is not established by these fixes.

The demo's old call-only markers have no historical recipient proof; Telegram
acceptance is not Core acceptance or a human read receipt. Crash between API
acceptance and local persistence can still duplicate retry; a distributed
production dispatcher needs the actual Core contract/idempotency boundary.
Proof-log retention/collection and disk monitoring must also be accepted on the
target. Two old local logs were losslessly compressed after filling the workspace;
no deployment of a retention service is claimed.

**Next blocking gate:** exact loaded bridge/image/profile/provider/model truth
on the configured target, then original WAV + CallActor/FreeSWITCH trace and
real Core/test-recipient acceptance; subsequently the 100-call/full-load and
blind-listening gates in the product plan. Green source tests do not bypass them.
