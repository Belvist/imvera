# IMVERA VoiseUp — CLI contract (ADR-008 §16)

COMPOSE = docker compose -f docker/docker-compose.yml --env-file docker/.env.example
VOICE_COMPOSE = docker compose -f docker/docker-compose.voice.yml
PYTHON = python3
export PYTHONPATH := .

.PHONY: install test lint up down ps logs api-health contracts-check migrate doctor
.PHONY: models-prepare models-up voice-setup voice-up voice-doctor voice-down zoiper-info voice-e2e voice-sip-e2e
.PHONY: voice-open test-contracts test-dialogue-e2e test-persistence-e2e test-voice test-sip
.PHONY: test-pstn trace-bench test-isolation release-check

install:
	$(PYTHON) -m pip install -e ".[dev,api,mlx]"

test:
	$(PYTHON) -m pytest tests/ -q

lint:
	$(PYTHON) -m ruff check packages services tests scripts

contracts-check:
	$(PYTHON) -c "from packages.contracts import *; from packages.contracts.semantic import SemanticPayload; from packages.voice_runtime import pcm16_frame_bytes; from packages.core import create_call_record_store; print('OK')"

migrate:
	$(PYTHON) scripts/migrate.py

doctor:
	$(PYTHON) scripts/doctor.py

models-prepare:
	$(PYTHON) scripts/models_prepare.py

models-up:
	$(PYTHON) scripts/models_up.py

voice-setup: install
	$(PYTHON) scripts/zoiper_info.py
	$(PYTHON) scripts/models_prepare.py

voice-up:
	$(PYTHON) scripts/voice_up.py

voice-doctor:
	@$(PYTHON) scripts/voice_doctor.py

voice-down:
	$(PYTHON) scripts/voice_down.py

zoiper-info:
	$(PYTHON) scripts/zoiper_info.py

voice-e2e:
	@$(PYTHON) scripts/voice_e2e.py

voice-sip-e2e:
	@$(PYTHON) scripts/voice_sip_e2e.py

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

api-health:
	curl -sf http://127.0.0.1:8080/health/live | $(PYTHON) -m json.tool

voice-open:
	@echo "Zoiper: dial 7000 (see make zoiper-info)"
	@echo "Gateway WS: ws://127.0.0.1:9200/media/<call_id>"

test-contracts: contracts-check

test-dialogue-e2e:
	$(PYTHON) -m pytest tests/test_integrity.py tests/test_product_dialogue.py tests/test_investor_dialogue.py -q

test-persistence-e2e:
	$(PYTHON) -m pytest tests/test_pg_persistence.py -q

test-voice:
	@$(PYTHON) scripts/doctor.py || (echo "BLOCKED: configure STT/TTS/DB first" && exit 1)
	@echo "Run make voice-up then Zoiper E2E (make voice-e2e)"

test-sip:
	@$(PYTHON) scripts/test_sip.py

test-pstn:
	@echo "BLOCKED: PSTN trunk not in scope for Zoiper sprint"

trace-bench:
	@echo "BLOCKED: tools/voice_lab bench harness pending"

test-isolation:
	$(PYTHON) -m pytest tests/test_integrity.py::test_wrong_family_cannot_read -q

release-check:
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) doctor
