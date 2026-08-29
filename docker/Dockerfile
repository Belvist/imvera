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
COPY voice_runtime /app/voice_runtime
COPY refs /app/refs
COPY scripts /app/scripts

# Models are NOT baked into the image anymore (the image was ~4 GiB and a
# rebuild re-pinned stale weights). Everything lives in the /data/models
# volume and downloads at first boot:
#   - Silero TTS ru v5    -> torch hub, $TORCH_HOME (voice service)
#   - Whisper STT         -> HuggingFace, $HF_HOME   (voice service)
#   - Qwen3-4B GGUF (LLM) -> llama_entrypoint.sh     (answers service)
# Volume = survives rebuilds; update = `make update` re-pulls images only.

# Keep runtime data out of the image layer.
RUN rm -rf /app/telephony/calls /app/telephony/__pycache__ \
        /app/telephony/tg/__pycache__ /app/telephony/tests/__pycache__ \
    && find /app -name "*.log" -delete \
    && mkdir -p /data/calls /data/models

ENV MOSS_RUNTIME_SCRIPTS=/app/runtime/scripts \
    HF_HOME=/data/models \
    TORCH_HOME=/data/models/torchhub \
    MOSS_TTS_MODEL_DIR=/data/models

EXPOSE 9400 9500 9600 8600
