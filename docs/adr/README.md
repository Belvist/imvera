# Architecture Decision Records

Record irreversible technical decisions here.

## Phase 1 (Architecture Freeze v1)

| ADR | Title | Status |
|-----|-------|--------|
| [001](001-telephony-asterisk-websocket.md) | Telephony: Asterisk ≥22.8 + dual media legs | accepted |
| [002](002-tts-silero-v5-phrase-chunked.md) | TTS: Silero v5_5_ru (historical) | **superseded** → [006](006-tts-benchmark-cosyvoice-qwen.md) |
| [002a](002a-silero-8k-vs-24k-benchmark.md) | Silero 8k vs 24k PSTN benchmark | deferred |
| [003](003-stt-whisper-streaming.md) | STT: Qwen3-ASR vs Whisper benchmark | accepted |
| [004](004-dialogue-fsm.md) | Dialogue FSM ownership | accepted |
| [005](005-status-precedence.md) | 4 axes + false-alarm protocol | accepted |
| [006](006-tts-benchmark-cosyvoice-qwen.md) | TTS: CosyVoice3 vs Qwen3-TTS | accepted |
| [007](007-unified-conversation-loop.md) | Unified conversation loop + CallSession | accepted |
| [008](008-product-milestones-voice-core.md) | Product milestones, Core boundary, semantic contract | accepted |

Master plan: [PLAN.md](../PLAN.md) v1.2
