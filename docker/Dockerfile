# syntax=docker/dockerfile:1.7
# IMVERA VoiseUp — greenfield voice stack
# Architecture Freeze v1 — see docs/PLAN.md

FROM python:3.12-slim-bookworm

ARG IMVERA_GIT_SHA=unknown
LABEL org.opencontainers.image.revision=$IMVERA_GIT_SHA

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY packages ./packages
COPY services ./services
COPY config ./config

RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -e '.[api,voice-runtime,semantic-nlp]'

ENV IMVERA_GIT_SHA=$IMVERA_GIT_SHA
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
