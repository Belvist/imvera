# LIVE PRODUCT GATE Report

**Updated (UTC):** 2026-09-04T01:00:00Z  
**Repo:** `/Users/earflow/Downloads/MossVoice`  
**GIT_SHA:** `0253ec8` (`git rev-parse --short HEAD`)  
**Scope:** HTTP/code gates + host Metal LLM; owner SIP still open.

## Final gate table (this session)

| Gate | Result | Evidence |
|------|--------|----------|
| Git identity | **PASS** (repo) | `0253ec8` |
| `/health` `build_sha` | **PASS** (after rebuild) | Image `MOSS_BUILD_SHA`; compose no longer forces `dev` on telephony |
| Host Metal LLM | **PASS** (host) | `:9500/health` ok; ~2.5 s gen; Docker `answers` profile off |
| `real_llm_conversation_eval --strict` | **PASS** | **6/6**; prior `llm_stream empty` = harness pool-first turns (no `llm_hint`) |
| `verify_hardening_gates.sh` | **PASS** (prior) | exit 0 |
| `make test-fast` | **PASS** (prior) | **464 OK** (29 skip) |
| `synthetic_caller.py --strict` | **PASS** (prior) | **30/30** |
| Live Zoiper / RTP | **RED** | Not exercised; HTTP ≠ SIP |
| `MOSS_LOCAL_ONLY=1` deploy | **RED** | Not enabled |

### Host LLM persistence (owner — after reboot)

```bash
cp scripts/run_llm_host.sh ~/Library/Application\ Support/MossVoice/ && chmod +x ~/Library/Application\ Support/MossVoice/run_llm_host.sh
cp scripts/com.mossvoice.llm.plist ~/Library/LaunchAgents/ && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mossvoice.llm.plist 2>/dev/null || launchctl load ~/Library/LaunchAgents/com.mossvoice.llm.plist
```

Verify: `curl -sf http://127.0.0.1:9500/health` · `tail -f /tmp/mossvoice_llm.log`

### `build_sha` fix

- **Root cause:** `docker-compose.yml` set `MOSS_BUILD_SHA: ${MOSS_BUILD_SHA:-dev}` on telephony, overriding image ENV with `dev` when the host did not export the variable.
- **Fix:** removed telephony runtime override; `make up` depends on `make build`; telephony service has `build.args` aligned with `voice`.
- **Verify:** `export MOSS_BUILD_SHA=$(git rev-parse --short HEAD) && make build && make up` then `curl -s http://127.0.0.1:9400/health | jq '.build_sha, .components.llm_detail'`

### P0 LLM check-in gate (`MOSS_DIALOGUE_LLM_CHECKIN`)

- **Before (call `e26d5338aed8`, live Zoiper):** symptom turn («голова болит») got LLM re-greet junk — «Здравствуйте», «чувствуетесь», «себе помочь» — instead of symptom follow-up.
- **Fix:** default **`MOSS_DIALOGUE_LLM_CHECKIN=0`** (`docker/docker-compose.yml`); `telephony/conversation_system/policy/llm_policy.py` forces pools on check-in/symptom when off; orchestrator cannot surface garbage LLM on those turns (`test_live_call_diag_fixes.py`).
- **After:** same utterance → pool line with **«беспокоит»** (e.g. «Мне жаль… что именно беспокоит?»); `allow_llm=false` on symptom path.
- **Verify:** `docker exec mossvoice-telephony printenv MOSS_DIALOGUE_LLM_CHECKIN` → `0`; `POST /calls` + `turn_text` «плохо голова болит тошнит» (HTTP smoke).

### `call_mirror llm_stream empty` (eval)

- **Harness:** turns with `allow_llm` but empty scenario `llm_hint` use pool/`spoken_reply`; eval no longer calls `reply_segments` without a hint.
- **Live:** OpenAI SSE stream reads `reasoning_content` when `content` deltas are empty (Qwen3 / llama.cpp).

## Session fixes (consolidated)

| Track | What changed | Verify |
|-------|----------------|--------|
| [Dialogue loop bugs](69b35f81-e574-4579-9916-34f7a62a14cb) | Closing phrases; mood slot; bad wellness yellow floor | `test_live_call_diag_fixes.py` |
| [synthetic_caller WAV](4d785e12-674a-45d5-9cf4-886c12168969) | Duplicate `?` on stream tail | `synthetic_caller --strict` **30/30** |
| [Host Metal LLM](c0448f93-78d8-4712-b927-68d8e7fa44fc) | `docs/HOST_LLM_METAL.md`, launchd plist | Host `:9500` ~2.5 s |

## Owner retest checklist (Zoiper — 3 scenarios)

After `make build && make up`:

1. **Closing** — «Вера, пока» → одно прощание.
2. **Mood → sleep** — настроение → вопрос про **сон**.
3. **Bad path + yellow** — симптом, не повтор mood; семья **yellow**.

## Still RED / not verified

- Live **Zoiper** + **RTP** + client mic
- **`MOSS_LOCAL_ONLY=1`** production fail-fast
- **Smart Turn** / latency baseline on live SIP

## Honesty

HTTP harness does **not** replace one live Zoiper call per AGENTS.md owner gate.
