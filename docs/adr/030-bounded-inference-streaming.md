# ADR-030: Bounded inference production and immediate PCM delivery

Date: 2026-10-03
Status: accepted for implementation; M5 and audible acceptance NOT VERIFIED

## Current system and bottleneck

The active path is final STT → SDK Understand/Reducer/selection → canonical
validated speech → CallActor._speak_phrase → HttpTTSProvider → /v1/synthesize
→ TTS producer → PlaybackQueue → FreeSWITCH. CallActor already consumes PCM
while synthesis runs. Its canonical speech ledger remains the sole delivery
owner. No production source/endpoint/flags on the owner's M5 were available
in this environment: this is a source audit, not a diagnosis of a recorded call.

MLX and Qwen TTS already emit incremental audio; Silero apply_tts materializes
an entire utterance before emitting its first PCM. The LLM renderer already
emits token deltas, but is excluded from the active SDK path by ADR-025.
Streaming cannot eliminate model prefill, final-STT or endpointing latency.

The TTS worker currently pairs a bounded queue with blocking put/get and waits
for its producer after the consumer disconnects. A full queue has no remaining
consumer: one disconnect can occupy its only inference thread forever.
HttpTTSProvider also omits the worker deadline; host monotonic clocks must not
be compared. This creates unbounded stale work rather than useful concurrency.

## Decision and owners

Replace the TTS HTTP stream's blocking queue bridge with one bounded stream
owned by the existing InferenceExecutor. Model work runs on its existing single
thread; HTTP consumption and CallActor playback run concurrently on the event
loop. A consumer disconnect, explicit cancellation or local deadline interrupts
queue waits. The executor retains its capacity until the real job completes;
queued abandoned jobs can be cancelled. No extra blocked thread per stream.
Admission occurs before response headers, with retryable overload status.

Send remaining timeout_ms to the worker and establish its deadline locally.
Legacy deadline remains accepted for same-host callers only. Do not change
engine state, speech, phrase/generation IDs, completion ledger, or SDK writer
fencing. Errors after partial audio remain errors; never replay another voice
or mark a partial utterance successfully delivered.

For batch-only Silero, an explicit operator flag IMVERA_TTS_SENTENCE_STREAM=1
allows synthesis at sentence boundaries without changing text/order. Never
split decimal values or abbreviations speculatively. This is sentence streaming,
not native incremental model decoding. It remains OFF until paired M5 audio
proves acceptable joins/prosody. MLX/Qwen retain their native streaming.

## Alternatives and cost

| Choice | First PCM | Resources | Delivery risk |
|---|---|---|---|
| Full batch utterance | waits for all text | one model thread | long start |
| Bounded producer + consumer | incremental where provider supports it | one model thread, bounded queue, async consumer | cancellation must unblock producer |
| Many threads on one model | no demonstrated benefit | contended accelerator/model state | unsafe without model benchmark |

Choose bounded producer/consumer. Capacity scales through the existing replica
pool and measured admission, not unrestricted model threads. No new model
calls for native streaming; optional Silero sentence mode adds one apply_tts
invocation per sentence. No new LLM calls; generation policy is unchanged.

## Migration, risks and acceptance

First reproduce disconnect/backpressure failure and missing deadline. Then
replace bridge, preserve existing error/fallback contracts, and prove first PCM
can precede synthesis completion using the actual HTTP adapter and CallActor.
Measure this separately from real-model M5 latency. Provide a real HTTP
benchmark tool for p50/p95/first PCM/full completion and stamped endpoint/voice.

Risks: an already-running model kernel cannot be preempted by Python; cancellation
is checked at queue/provider boundaries. Sentence mode may add audible joins or
increase total compute. STT remains final utterance recognition. No claims of
100 concurrent calls, million users or human warmth follow from unit tests.

NEXT GATE: paired M5 end-of-speech→first PCM→first transport send traces, real
SIP recordings, interruption under backpressure and concurrent capacity probe.
