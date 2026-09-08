# Perception service gate

Standalone Docker service for the uplink perception layer (echo gate, turn FSM, text echo).

## Stack

```text
FreeSWITCH → media-bridge (transport) → CallActor
                                              ↳ PerceptionSession (in-process default)
                                              ↳ imvera_perception:9110 (optional remote / lab)
```

Production hot path uses **in-process** `PerceptionSession` inside CallActor (zero extra hop).
The Docker service is for isolated development, CI, and perception-only tests without MLX/STT.

## Run

```bash
make perception-up
make perception-health
```

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /health/ready` | readiness |
| `POST /v1/sessions` | create per-call session |
| `POST /v1/downlink` | push Vera PCM reference |
| `POST /v1/text_echo` | check STT text echo |
| `WS /v1/stream/{call_id}` | frame-by-frame uplink decisions |

## Env

Same flags as CallActor lab:

- `IMVERA_ECHO_REF_GATE=1` — acoustic echo gate (default on in compose)
- `IMVERA_LAB_HALF_DUPLEX=0` — always-listen
- `IMVERA_UPLINK_PREROLL_MS=300`
- `IMVERA_POST_SPEECH_PAUSE_MS=100`

## Tests

```bash
pytest tests/test_voice_perception.py tests/test_forensic_gate.py tests/test_uplink_preroll.py
```
