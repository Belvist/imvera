# syntax=docker/dockerfile:1.7
# Same worker contracts on Linux; no MLX or lab voice dependencies.
ARG PYTHON_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_IMAGE} AS tts-http
ARG IMVERA_GIT_SHA
LABEL org.opencontainers.image.revision=$IMVERA_GIT_SHA
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
    IMVERA_RUNTIME_MODE=production IMVERA_WORKER_HOST=0.0.0.0 \
    IMVERA_VOICE_PROFILE_PATH=/app/config/voice-linux-cpu.yaml \
    IMVERA_GIT_SHA=$IMVERA_GIT_SHA
COPY pyproject.toml README.md ./
COPY packages ./packages
COPY services ./services
COPY config ./config
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -e '.[api,voice-runtime]'
USER 10001:10001
EXPOSE 9102
CMD ["python", "-m", "services.tts.worker"]

FROM tts-http AS stt-cpu
USER root
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca GIT_SSL_CAINFO=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir torch==2.11.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -e '.[gigaam-stt]'
USER 10001:10001
EXPOSE 9101
CMD ["python", "-m", "services.stt.worker"]
