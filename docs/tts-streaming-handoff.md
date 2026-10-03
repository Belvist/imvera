# TTS streaming integration and M5 acceptance

Branch **feature/voice-zoiper-m5**. Decision: [ADR-030](adr/030-bounded-inference-streaming.md).
This changes the actual `/v1/synthesize`/`HttpTTSProvider` path used by CallActor;
there is no separate delivery engine. Generative SDK speech remains disabled.

## Runtime contract

Deploy the matching bridge/provider and TTS worker source together using the
existing deployment runbook in a no-call window. No live restart was performed
by this change. The new provider sends remaining `timeout_ms`; worker monotonic
deadlines are established on the worker host, and cover admission wait and
output production. Existing same-host `deadline` callers remain supported.

One model thread produces chunks; an async HTTP consumer forwards them while
CallActor feeds its existing bounded PlaybackQueue and transport pump. At most
8 output chunks are queued. There is no blocked reader thread per call. Overload
is 429 before response headers. Disconnect/explicit cancel unblocks queue waits;
a running kernel retains its admission slot until it actually settles. Do not
raise model thread counts or call caps without a measured capacity probe.

Generation ID, phrase ID, canonical text and playout ledger are unchanged.
HTTP `done` must arrive; EOF after PCM is failure, never successful delivery or
permission to replay another replica. Request-ID and generation cancellation
both terminate worker output. Producer errors after a sentinel are still errors.

MLX and Qwen retain native chunk delivery. Silero is batch-only: optional
`IMVERA_TTS_SENTENCE_STREAM=1` **on the TTS worker** synthesizes complete sentences
sequentially, forwarding initial PCM while later sentences are prepared. Decimal
numbers/initials/abbreviations are conservatively kept together. Default is0,
and the flag has no effect on native streaming providers. This is an acoustic
optimization, not wording generation. Keep it OFF until audio comparison passes.
Silero remains the existing lab reference; the flag does not change provider or
production eligibility.

## Measure the actual worker first

Record deployed SHA, PID/launch configuration, hardware, voice revision, flags,
STT/TTS endpoints and routing. `/health/ready` now exposes true queue depth but
does not establish deployed git SHA. Benchmark output deliberately separates
local tool SHA from unknown worker SHA. Use the existing version watch/runbook
for source alignment; retain the full worker launch evidence.

From the checkout with its normal virtual environment and warmed worker:

```bash
PYTHONPATH=. python tools/voice_lab/tts_stream_benchmark.py \
  --url http://127.0.0.1:9102 --runs 30 --concurrency 1 \
  --label 'M5; exact voice revision; sentence_stream=0; deployed SHA recorded separately' \
  --output .run/tts-stream-before.json
```

If the active provider is Silero and sentence joins are being evaluated, restart
only that worker using its existing launch procedure with the flag1, then repeat
with the identical text/voice and output `.run/tts-stream-after.json`. Revert the
flag if p95, failures, total compute or audible joins worsen. For MLX/Qwen,
compare old/new worker source with the same native streaming configuration.

The tool makes real HTTP requests through HttpTTSProvider, excludes one warmup,
records successful first-PCM/completion p50/p95, individual chunks/audio duration,
actual readiness and errors. Failed runs cause a nonzero exit. It does not
measure speech-end or audibility; successful-only percentiles must be considered
alongside the error count. Increase `--concurrency` only within operator-admitted
limits and compare errors/queue saturation; this does not raise call caps.

## Phone gate and limits

Then use the existing FreeSWITCH/Zoiper7000 route and capture audio plus trace:
`speech_end → endpoint → stt_final → decision → tts.start → tts.first_pcm →
playout.first_send`, cancellation timestamps/generation and final ledger.
Native STT is still final recognition; prefix observations are not final text.
Measure p50/p95 per boundary with the same utterances before/after. HTTP first
PCM is distinct from first transport send and audible sound.

Test interruption after initial audio and during backpressure. No subsequent
cancelled-generation PCM may be sent; the interrupted action must not become
DELIVERED. Preserve the existing protected-turn barge-in policy and flags.

CHANGED: bounded streaming, relative deadlines, completion integrity, optional
sentence batching and reproducible measurement. VERIFIED: controlled producer,
real TCP HTTP/provider/CallActor delivery and cancellation; see evidence.
NOT VERIFIED: actual M5 speed, SIP/audio, joins/prosody, deployment, scale.
REMAINING RISKS: model kernel preemption, batch voice prosody/extra inference,
final STT and model throughput. NEXT GATE: paired actual M5 phone/audio traces.
