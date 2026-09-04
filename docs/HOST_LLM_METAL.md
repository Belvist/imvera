# Host LLM on Metal (llama.cpp)

Telephony’s `CallMirror.reply_stream` waits only a few seconds for the LLM.
The Docker `answers` service runs **CPU-only Linux** llama.cpp (~8.5 s per
reply) and almost always falls back to script pools. The fix is the same
pattern as STT on `:9705`: run **llama-server on the Mac host** with Metal
GPU layers and point telephony at `host.docker.internal:9500`.

## Prerequisites

```bash
brew install llama.cpp
```

First run downloads the pinned Qwen3-4B Q4_K_M GGUF (~2.5 GB) into:

`~/Library/Application Support/MossVoice/models/llm/Qwen3-4B-Q4_K_M.gguf`

If you already ran `docker compose --profile local-llm up answers`, the
host script reuses the file from the Docker `models` volume when found.

## Start manually (foreground)

```bash
bash scripts/run_llm_host.sh
# health: curl -sf http://127.0.0.1:9500/health
```

Useful env overrides:

| Variable | Default | Purpose |
|----------|---------|---------|
| `MOSS_LLM_N_GPU_LAYERS` | `99` | Metal offload (0 = CPU only) |
| `MOSS_LLM_THREADS` | `4` | CPU threads for partial layers |
| `MOSS_LLM_CTX` | `4096` | Context size |
| `MOSS_LLM_GGUF_FILE` | see above | Explicit model path |
| `MOSS_LLM_PORT` | `9500` | Bind port |

## launchd (recommended)

launchd may not execute scripts under `~/Downloads`. Copy the launcher once:

```bash
cp scripts/run_llm_host.sh ~/Library/Application\ Support/MossVoice/
chmod +x ~/Library/Application\ Support/MossVoice/run_llm_host.sh
cp scripts/com.mossvoice.llm.plist ~/Library/LaunchAgents/
# Edit MOSS_REPO in the plist if your repo path differs.
launchctl unload ~/Library/LaunchAgents/com.mossvoice.llm.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.mossvoice.llm.plist
launchctl start com.mossvoice.llm
tail -f /tmp/mossvoice_llm.log
```

## Docker telephony wiring

Do **not** start the compose `answers` profile when using host LLM (same port
9500). In `docker/.env`:

```bash
MOSS_LLM_PROVIDER=local
MOSS_LLM_PROTOCOL=openai
MOSS_LLM_URL=http://host.docker.internal:9500
MOSS_LLM_TIMEOUT_S=8
```

Then `make up` (without `--profile local-llm`). The `local-llm` Docker service
remains available as an offline Linux CPU fallback:

```bash
docker compose --profile local-llm up -d answers
```

## Expected latency

| Backend | Typical first-token / short reply |
|---------|-----------------------------------|
| Docker `answers` (Linux CPU) | ~8–9 s |
| Host Metal (`--n-gpu-layers 99`) | ~0.5–2 s |

With `MOSS_LLM_TIMEOUT_S=8`, `CallMirror` can consume streamed LLM output
instead of pool fallbacks on most turns.

## Verify

```bash
curl -sf http://127.0.0.1:9500/health
curl -sf http://127.0.0.1:9500/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"local","messages":[{"role":"user","content":"Привет"}],"max_tokens":40,"stream":false,"thinking":false}'
```
