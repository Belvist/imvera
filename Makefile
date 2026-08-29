# MossVoice — единый цикл сборки и тестов (prod = docker).
#
#   make build      собрать production-образ mossvoice/backend:latest
#   make test       собрать + автотесты ВНУТРИ контейнера (офлайн-сьют)
#   make test-fast  офлайн-сьют в готовом образе, /app/telephony смонтирован
#                   из рабочей копии — БЕЗ пересборки
#   make test-live  автотесты + HTTP-интеграция с live TTS-демоном в compose
#   make up         собрать и поднять ВЕСЬ стек (db/cache/storage/voice/
#                   answers/telephony; первый старт качает модели в volume)
#   make release    ЕДИНСТВЕННЫЙ официальный packaging path (read.md rev-3 G0):
#                   git archive allowlist -> scan -> sha256 -> ZIP. Никакого
#                   Finder→Compress — иначе в ZIP попадут calls/.env/log.
#   make update     пересобрать образы (--pull) и перезапустить стек
#   make ps         статус сервисов
#   make logs       логи всего стека (Ctrl-C, чтобы выйти)
#   make stop       остановить прод-стек (данные в volume сохраняются)
#
# Главное правило: тесты идут в том же образе, что и прод. Никакого
# "локального питона с отдельными зависимостями".

IMG      ?= mossvoice/backend:latest
COMPOSE  ?= docker compose -f docker/docker-compose.yml

.PHONY: build test test-fast test-live up update ps stop logs clean db-up db-down test-db test-data release migrate

build:
	docker build -f docker/Dockerfile -t $(IMG) .

migrate:
	# Schema-migration JOB (read.md rev-3): DDL runs here, one-shot, before
	# the realtime rollout. Independent of the rest of the stack.
	$(COMPOSE) build migrate
	$(COMPOSE) run --rm migrate

test: build
	MOSS_IMAGE=$(IMG) $(COMPOSE) --profile tests run --rm tests

test-fast:
	MOSS_IMAGE=$(IMG) $(COMPOSE) --profile tests run --rm \
		-v "$(CURDIR)/telephony:/app/telephony" tests

# Data-core drills: real Postgres/Redis/MinIO + integration suite.
db-up:
	$(COMPOSE) up -d db cache storage

db-down:
	$(COMPOSE) stop db cache storage

test-db:
	$(COMPOSE) up -d db cache
	MOSS_PG_URL=postgresql://mossvoice:mossvoice_dev@127.0.0.1:5432/mossvoice \
	MOSS_REDIS_URL=redis://127.0.0.1:6379/0 \
		"$(HOME)/Library/Application Support/MossVoice/runtime/qwen-venv/bin/python" \
		-m unittest discover -s telephony/tests -t telephony -v; st=$$?; \
		$(COMPOSE) stop db cache; exit $$st

# Integration-data tier (read.md rev-3): REAL Postgres/Redis/MinIO in compose,
# migrations applied, then the full suite inside the container. (Unit tier is
# `make test` — no data deps, offline-safe.)
test-data:
	$(COMPOSE) up -d db cache storage
	$(COMPOSE) run --rm migrate
	MOSS_IMAGE=$(IMG) $(COMPOSE) --profile tests run --rm tests-data; st=$$?; \
		$(COMPOSE) stop db cache storage; exit $$st

test-live: build
	MOSSTEST_TTS=http://voice:9600 MOSSTEST_WAIT_DAEMON=1 \
		MOSS_IMAGE=$(IMG) $(COMPOSE) --profile tests up -d voice
	MOSSTEST_TTS=http://voice:9600 MOSSTEST_WAIT_DAEMON=1 \
		MOSS_IMAGE=$(IMG) $(COMPOSE) --profile tests run --rm \
		-e MOSSTEST_TTS=http://voice:9600 -e MOSSTEST_WAIT_DAEMON=1 tests; st=$$?; \
		MOSS_IMAGE=$(IMG) $(COMPOSE) --profile tests stop voice; \
		MOSS_IMAGE=$(IMG) $(COMPOSE) --profile tests rm -f voice; \
		exit $$st

up:
	# Schema first (migration JOB owns DDL); telephony is gated on its success.
	$(COMPOSE) up -d --build db
	$(COMPOSE) run --rm migrate
	$(COMPOSE) up -d --build

update:
	$(COMPOSE) build --pull
	$(COMPOSE) up -d

ps:
	$(COMPOSE) ps

stop:
	$(COMPOSE) stop

logs:
	$(COMPOSE) logs --tail=200 -f

clean:
	$(COMPOSE) down -v --remove-orphans

release:
	bash scripts/make_release.sh
