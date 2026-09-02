#!/usr/bin/env bash
# Deploy MossVoice v1 stack: Nemotron ASR + Qwen3-TTS host services.
# Usage: bash scripts/deploy_stack.sh [start|stop|status|restart]
set -uo pipefail

REPO="${MOSS_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PLIST_DIR="$HOME/Library/LaunchAgents"

nemotron_plist="$PLIST_DIR/com.mossvoice.nemotron.plist"
qwen3_plist="$PLIST_DIR/com.mossvoice.qwen3-tts.plist"

stop_service() {
    label="$1"
    launchctl unload "$PLIST_DIR/$label.plist" 2>/dev/null || true
    launchctl remove "$label" 2>/dev/null || true
    echo "stopped $label"
}

load_service() {
    label="$1"
    plist="$PLIST_DIR/$label.plist"
    if [ ! -f "$plist" ]; then
        echo "ERROR: $plist not found" >&2
        return 1
    fi
    launchctl unload "$plist" 2>/dev/null || true
    launchctl load "$plist"
    launchctl start "$label"
    echo "started $label"
}

status_service() {
    label="$1"
    if launchctl list 2>/dev/null | grep -q "$label"; then
        echo "$label: RUNNING"
    else
        echo "$label: STOPPED"
    fi
}

case "${1:-start}" in
    start)
        echo "=== Deploying MossVoice v1 stack ==="
        load_service com.mossvoice.nemotron
        load_service com.mossvoice.qwen3-tts
        echo "=== Host services started ==="
        echo "Nemotron:  http://127.0.0.1:9710/ready"
        echo "Qwen3-TTS: http://127.0.0.1:9711/ready"
        echo "Models must be downloaded before services are ready:"
        echo "  huggingface-cli download nvidia/nemotron-3.5-asr-streaming-0.6b"
        echo "  huggingface-cli download Qwen/Qwen3-TTS-12Hz-0.6B-Base"
        echo "Then: launchctl stop com.mossvoice.nemotron && launchctl start com.mossvoice.nemotron"
        ;;
    stop)
        echo "=== Stopping MossVoice v1 stack ==="
        stop_service com.mossvoice.nemotron
        stop_service com.mossvoice.qwen3-tts
        ;;
    restart)
        echo "=== Restarting MossVoice v1 stack ==="
        stop_service com.mossvoice.nemotron
        stop_service com.mossvoice.qwen3-tts
        sleep 1
        load_service com.mossvoice.nemotron
        load_service com.mossvoice.qwen3-tts
        ;;
    status)
        echo "=== MossVoice v1 stack status ==="
        status_service com.mossvoice.nemotron
        status_service com.mossvoice.qwen3-tts
        echo "--- ports ---"
        lsof -iTCP:9710 -sTCP:LISTEN 2>/dev/null | grep LISTEN || echo "9710 (nemotron): not listening"
        lsof -iTCP:9711 -sTCP:LISTEN 2>/dev/null | grep LISTEN || echo "9711 (qwen3-tts): not listening"
        echo "--- health ---"
        curl -s http://127.0.0.1:9710/ready 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "nemotron /ready: unreachable"
        curl -s http://127.0.0.1:9711/ready 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "qwen3-tts /ready: unreachable"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}" >&2
        exit 1
        ;;
esac
