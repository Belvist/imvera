# Architecture Decision Records

Record irreversible technical decisions here.

## Phase 1 (Architecture Freeze v1)

| ADR | Title | Status |
|-----|-------|--------|
| [001](superseded/001-telephony-asterisk-websocket.md) | Telephony: Asterisk ≥22.8 + dual media legs | accepted |
| [002](superseded/002-tts-silero-v5-phrase-chunked.md) | TTS: Silero v5_5_ru (historical) | **superseded** → [006](006-tts-benchmark-cosyvoice-qwen.md) |
| [002a](002a-silero-8k-vs-24k-benchmark.md) | Silero 8k vs 24k PSTN benchmark | deferred |
| [003](003-stt-whisper-streaming.md) | STT: Qwen3-ASR vs Whisper benchmark | accepted |
| [004](004-dialogue-fsm.md) | Dialogue FSM ownership | accepted |
| [005](005-status-precedence.md) | 4 axes + false-alarm protocol | accepted |
| [006](006-tts-benchmark-cosyvoice-qwen.md) | TTS: CosyVoice3 vs Qwen3-TTS | accepted |
| [007](007-unified-conversation-loop.md) | Unified conversation loop + CallSession | accepted |
| [008](008-product-milestones-voice-core.md) | Product milestones, Core boundary, semantic contract | accepted |
| [010](010-directional-media-plane.md) | Directional media plane: spy=in, MediaHealth, 4-layer counters | accepted |
| [011](superseded/011-telephony-adapter-telnyx.md) | Telnyx media stream (managed API) | **rejected** → [012](superseded/012-self-hosted-telephony-livekit.md) |
| [012](superseded/012-self-hosted-telephony-livekit.md) | Self-hosted LiveKit + LiveKit SIP; full stack on our servers | accepted |

## Production freeze (2026-09-08)

| ADR | Title | Status |
|-----|-------|--------|
| [013](013-production-telephony-freeswitch.md) | Production telephony: FreeSWITCH + PCM WS | accepted; freeze clauses amended → [023](023-replacement-and-cleanup-law.md) |
| [014](014-architecture-freeze-acceptance-gates.md) | Architecture freeze + 7 acceptance gates; no fourth system | accepted; blanket freeze amended → [023](023-replacement-and-cleanup-law.md) |

## Replacement law (2026-09-28)

| ADR | Title | Status |
|-----|-------|--------|
| [023](023-replacement-and-cleanup-law.md) | Replacement and cleanup law | accepted |
| [024](024-bounded-neuro-learning.md) | Bounded neuro learning and dialogue proof chain | accepted |
| [025](025-grounded-dialogue-sdk.md) | Grounded dialogue SDK and canonical act adjudication | accepted for implementation; live voice NOT VERIFIED |
| [026](026-grounded-warm-dialogue.md) | Grounded warmth through existing dialogue owners | accepted for implementation; live/human warmth NOT VERIFIED |

| [027](027-realtime-conversation-v1.md) | Realtime Conversation v1: endpointing, cancellation and measured delivery | runtime slice implemented; live voice NOT VERIFIED |
| [028](028-conversational-move-evolution.md) | Conversational move authority, measurement and constrained surface realization | proposed; Cut 0/Cut 1a implemented; authority/live voice NOT VERIFIED |

ADR-012 is **lab/spike only** for production telephony (see ADR-013).  
ADR-014 **does not** stamp `ARCHITECTURE = FROZEN` until gates 1–7 are VERIFIED.

Master plan: [PLAN.md](../PLAN.md) v1.2 (historical freeze candidate). Active freeze: ADR-014.

| [030](030-bounded-inference-streaming.md) | Bounded inference streaming and parallel PCM delivery | runtime slice implemented; M5/audio NOT VERIFIED |
