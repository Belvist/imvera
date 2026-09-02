# P4 — VoiceRuntime live verification checklist

> ROADMAP Э0. Loopback B-leg пишет пустой tap — **не годится** как E2E.
> Нужен реальный Zoiper/телефон на extension **4402** (dev) с VoiceRuntime.

## Preflight

1. `launchctl list | grep mossvoice` — `com.mossvoice.runtime` running
2. `curl -s http://127.0.0.1:9700/ready` → `esl_connected`, `agent_ok`
3. `curl -s http://127.0.0.1:9400/ready` → ready
4. Dialplan: 4402 = answer+sleep (или park); runtime regex `^44(0[012])$`
5. `MOSS_ESL_PASSWORD` загружен из `~/.fs_cli_conf`

## Test call

1. Zoiper → dial **4402** (один канал, не loopback originate).
2. Слушать greeting; сказать «раз два три» во время речи Веры (barge-in).
3. Сказать «всё хорошо» на вопрос самочувствия; попрощаться.

## Collect

| Check | How | Pass |
|-------|-----|------|
| Tap size > 1 KB | `/tmp/mossvoice/<call_id>/` or record path | |
| Channels | `ffprobe` / wave header: mono or stereo? | |
| LEFT = caller | If stereo: speech only on ch0 | |
| Echo | Transcript ≠ last Vera reply | |
| Barge-in | Playback stops ≤300 ms (log timestamps) | |
| LATENCY | docker/runtime logs: stt/llm/tts/first_audio | |

## Decision (fill after call)

- [ ] Stereo direction-split works → keep LEFT-only path
- [ ] Mono mix only → keep server echo-guard; MediaAdapter must use media-bug
- [ ] Tap empty / EARLY → do **not** cutover 4400; stay on Lua until fixed

Date: ________  Call-id: ________  Operator: ________
