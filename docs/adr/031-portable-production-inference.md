# ADR-031: Portable production inference and bounded request lifetime

Date: 2026-10-03
Status: accepted for implementation; actual deployment/model/audio NOT VERIFIED

## Context / current owners

DialogueEngine/Reducer and CallActor/provider contracts are already portable
Python/Linux. MLX is an Apple-specific inference backend, not the dialogue core.
Workers hardcode config/voice-m5.yaml despite the bridge's existing
IMVERA_VOICE_PROFILE_PATH resolver. TTS generation/request cancellation sets grow
without a lifetime bound. TTS accepts ambiguous unbounded IDs/deadlines, cannot
reject duplicate live request IDs, and Qwen failures can invoke lab Silero.
Qwen HTTP reads fill a0.4s buffer before yielding and can wait120s despite a
shorter turn deadline. Deployment has a Linux bridge image but no portable TTS
worker launch artifact. This is a source audit, not loaded M5/server diagnosis.

## Decision

Reuse the existing profile resolver across workers. Production is an explicit
IMVERA_RUNTIME_MODE=production contract: require an explicit profile, source SHA,
known backend and bounded service limits. Linux must reject Apple-only backends;
production must reject lab voices and lab fallback. Keep existing lab behavior
when explicitly using the lab mode; no second dialogue/speech owner is created.
Prepare a Linux profile using existing GigaAM and the existing Qwen HTTP/PCM
backend, with the actual resident inference server supplied as a pinned external
artifact. Do not invent a CUDA image, model quality or capacity. The same Python
bridge/worker code runs on Mac and Linux; only backend/profile/dependencies differ.

Replace TTS unbounded cancellation sets with one thread-safe registry. Active
requests have cancellation Events retained until consumer AND producer settle;
unknown/early/late cancellations use bounded expiring tombstones. Generation
cancellation reaches every active phrase. Duplicate live request IDs fail409.
Registration is rolled back on overload/failure. Active HTTP leases also have
a32-stream ceiling; completed producers cannot admit unlimited stalled clients.
The response deadline includes blocked ASGI writes, not only model/queue waits. Inputs and deadlines are finite
and bounded. Ready metadata must expose code/profile/backend and real queue state.

Bound queue memory by bytes as well as items, and interrupt queue waits on
cancellation/deadline/disconnect. No claim that Python can preempt a running
kernel: dedicated model-process watchdogs contain stuck jobs (default120s) and
stuck startup (default240s), exiting70 for supervisor restart; container stop
budgets bound shutdown. These guards never terminate the SDK/state writer. Model
capacity remains occupied until actual completion, never caller timeout.

For Qwen HTTP delivery, use non-buffer-filling reads, bounded connect/read/total
budgets, cancellation between reads and guaranteed connection cleanup. Preserve
partial-audio error semantics and disable any lab fallback in production.

## Migration and alternatives

1. Red contracts: cancellation storms, active cancellation despite eviction,
   duplicate IDs, memory bound, remote read stalls and first short PCM.
2. Replace cancellation/config/read owner in the existing worker/adapter.
3. Produce a Linux worker image and checked launch configuration (private bind,
   resource/queue/deadline limits, SHA, stop budget and mounted model artifacts).
4. Run source/HTTP/container fault gates, then real model/SIP/load acceptance.

| Option | Portability | Cost | Risk |
|---|---|---|---|
| Keep Mac-only worker config | low | low now | later platform migration |
| Same contracts + explicit platform backend | high | per deployed model | requires model/audio benchmark |
| Rewrite dialogue for Linux | unnecessary | high | competing state owner |

Choose the second. No model/provider selection change on the current M5. STT and
TTS inference server artifacts must be pinned and measured on target hardware;
CPU and GPU capacity cannot be inferred from a YAML file or controlled fixtures.

## Acceptance and limits

Safety/state/canonical speech unchanged. Prove bounded memory/cancel storms,
actual slot retention, partial stream failures, portable profile selection and
production rejection of fallback. Linux image must build and run without MLX;
missing real backend/model must fail readiness, not masquerade as ready.
No actual server address/GPU/model endpoint is supplied yet. Product acceptance
still requires actual hardware models, consent/Core/SIP audio, latency and soak.
