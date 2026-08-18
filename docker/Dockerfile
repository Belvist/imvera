# MossVoice backend runtime for Docker (Linux CPU).
#
# One image, many commands: voice / answers / telephony (+ telegram profile).
# TTS: MOSS-TTS-Nano ONNX (torch-free, zero-shot voice clone, CPU).
# STT: Whisper via transformers. LLM (answers): Qwen3 via transformers.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TOKENIZERS_PARALLELISM=false \
    MOSS_NO_VENV=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# MOSS-TTS-Nano runs on onnxruntime only. torch is still needed for the
# transformers LLM backend (answers) and Whisper STT fallback.
RUN pip install --no-cache-dir torch==2.13.0 torchaudio==2.11.0 \
        --index-url https://download.pytorch.org/whl/cpu
COPY docker/requirements.lock /app/docker/requirements.lock
RUN pip install --no-cache-dir -r /app/docker/requirements.lock

WORKDIR /app

COPY runtime/scripts /app/runtime/scripts
COPY telephony /app/telephony
COPY refs /app/refs
COPY scripts /app/scripts

# Ship the MOSS-TTS-Nano weights inside the image. Never COPY from the repo:
# weights are excluded from git/ZIP and are instead downloaded pinned to a
# known-good HF revision and verified against scripts/models.sha256. Docker
# layer-caches this step, so rebuilds do not re-download.
RUN python3 /app/scripts/download_models.py /data/models \
    && rm -rf /data/models/*/.cache

# Keep runtime data out of the image layer.
RUN rm -rf /app/telephony/calls /app/telephony/__pycache__ \
        /app/telephony/tg/__pycache__ /app/telephony/tests/__pycache__ \
    && find /app -name "*.log" -delete \
    && mkdir -p /data/calls /data/models

ENV MOSS_RUNTIME_SCRIPTS=/app/runtime/scripts \
    HF_HOME=/data/models \
    MOSS_TTS_MODEL_DIR=/data/models

EXPOSE 9400 9500 9600 8600
