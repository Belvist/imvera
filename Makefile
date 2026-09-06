# IMVERA VoiseUp

COMPOSE = docker compose -f docker/docker-compose.yml --env-file docker/.env.example

.PHONY: install test lint up down ps logs api-health contracts-check

install:
	python3 -m pip install -e ".[dev,api]"

test:
	python3 -m pytest tests/ -q

lint:
	python3 -m ruff check packages services tests

contracts-check:
	python3 -c "from packages.contracts import *; from packages.status import StatusEngine; print('OK')"

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

api-health:
	curl -sf http://127.0.0.1:8080/health | python3 -m json.tool
