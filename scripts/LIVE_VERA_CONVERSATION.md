# Live Vera Conversation Tester

Real FreeSWITCH call-path harness — **not** `turn_text` and not pure HTTP synthetic.

## What it does

1. **Originate** `loopback/4400` (or `4403`) via ESL — same stack as Zoiper.
2. **Inject** caller speech with `uuid_broadcast` on the **loopback A-leg** (verified).
3. **Capture** Vera replies from `/tmp/mossvoice/<call_id>/reply-*.wav`.
4. **Transcribe** replies with host STT (`MOSS_STT_HOST`, default `:9705`).
5. **Evaluate** dead-ends, clarify loops, safety, agenda movement.

## Prerequisites

- FreeSWITCH running (`fs_cli status`)
- `telephony` healthy @ `http://127.0.0.1:9400`
- Host STT @ `http://127.0.0.1:9705/ready`
- `MOSS_ESL_PASSWORD` or `~/.fs_cli_conf`
- macOS `say` + `ffmpeg` for user phrase WAVs

## Usage

```bash
# Default: 3 scenarios on prod extension 4400 (VoiceRuntime)
python3 scripts/live_vera_conversation.py

# Single scenario + JSON report
python3 scripts/live_vera_conversation.py --scenario good_path \
  --report /tmp/live_vera_report.json

# Lua test route (extension 4403 — install deploy/freeswitch/dialplan_moss_lua_test.xml)
python3 scripts/live_vera_conversation.py --extension 4403

# Strict exit code
python3 scripts/live_vera_conversation.py --strict
```

## Honest limits (read this)

| Topic | Reality on this Mac |
|-------|---------------------|
| **Dialplan 4400** | `answer` + `park` → **VoiceRuntime** (ESL). Lua (`moss_agent.lua`) is **not** on 4400. |
| **Loopback audio** | B-leg has no real RTP. Caller speech is injected via **A-leg** `uuid_broadcast`. |
| **Zoiper** | Registered (`1000`); `--originate bridge` rings the app — not automated here. |
| **vs synthetic_caller** | That harness uses HTTP `turn_stream`; this one drives **FS + runtime/Lua + turn_stream**. |

## Scenarios

| Name | Turns | Checks |
|------|-------|--------|
| `good_path` | wellness → mood → sleep → plans | agenda moves, record-notify |
| `bad_symptom` | плохо → голова → сильно | symptom depth |
| `greeting_back` | здравствуйте → хорошо → нормально | greeting-back |
| `critical_fall` | я упал | safety language |
| `goodbye` | всё хорошо → до свидания | closing |

## Install Lua test extension (optional)

```bash
cp deploy/freeswitch/dialplan_moss_lua_test.xml \
  /opt/homebrew/Cellar/freeswitch/*/etc/freeswitch/dialplan/default/
cp telephony/moss_agent.lua \
  /opt/homebrew/Cellar/freeswitch/*/etc/freeswitch/scripts/
fs_cli -x reloadxml
python3 scripts/live_vera_conversation.py --extension 4403
```
