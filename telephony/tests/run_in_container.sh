#!/bin/sh
# Runs the MossVoice test suite INSIDE the production docker image.
#   make test      -> offline suite (daemon-HTTP tests skip themselves)
#   make test-live -> waits for MOSSTEST_TTS, then runs everything incl. HTTP
set -e
cd /app/telephony

# Tests construct Serve with fake engines; the real Whisper warmup would
# load ~2.5GiB into this container and OOM the Docker VM next to the live
# voice daemon (which already holds its own models).
export MOSS_NO_WARMUP=1

if [ -n "${MOSSTEST_WAIT_DAEMON:-}" ] && [ -n "${MOSSTEST_TTS:-}" ]; then
  echo "[tests] waiting for $MOSSTEST_TTS (up to 10 min for model download)..."
  i=0
  while [ "$i" -lt 120 ]; do
    if python -c "import urllib.request,json,sys; sys.exit(0 if json.load(urllib.request.urlopen('$MOSSTEST_TTS/health',timeout=3)).get('ready') else 1)" 2>/dev/null; then
      echo "[tests] daemon ready"
      break
    fi
    i=$((i+1))
    sleep 5
  done
fi

exec python -m unittest discover -s tests -v
