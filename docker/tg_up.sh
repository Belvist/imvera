#!/bin/zsh
# Bring up the MossVoice Telegram profile in Docker.
#
# cloudflared prints a fresh trycloudflare URL; this script waits for it,
# then starts the bot container with that URL (and the rest of the stack).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ -z "${MOSSVOICE_BOT_TOKEN:-}" ]]; then
  TOKEN_FILE="$(dirname "$DIR")/telephony/tg/bot.token"
  [[ -f "$TOKEN_FILE" ]] && export MOSSVOICE_BOT_TOKEN="$(tr -d '\n' < "$TOKEN_FILE")"
fi
if [[ -z "${MOSSVOICE_BOT_TOKEN:-}" ]]; then
  echo "ERROR: set MOSSVOICE_BOT_TOKEN or keep telephony/tg/bot.token" >&2
  exit 1
fi

echo "[tg-docker] starting core services + tunnel..."
docker compose -f "$DIR/docker-compose.yml" --profile telegram up -d \
  --scale bot=0 ${@:1} || docker compose -f "$DIR/docker-compose.yml" --profile telegram up -d voice answers telephony tg cloudflared ${@:1}

# Wait for the tunnel URL from the cloudflared container logs.
URL=""
for i in {1..60}; do
  URL="$(docker logs mossvoice-tunnel 2>&1 | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1)"
  [[ -n "$URL" ]] && break
  sleep 1
done
if [[ -z "$URL" ]]; then
  echo "ERROR: no trycloudflare URL from mossvoice-tunnel logs" >&2
  docker logs mossvoice-tunnel 2>&1 | tail -5
  exit 1
fi
echo "[tg-docker] tunnel ready: $URL"

WEBAPP_URL="$URL" docker compose -f "$DIR/docker-compose.yml" --profile telegram up -d bot ${@:1}
echo "[tg-docker] bot started. Press «Позвонить» in Telegram."
