# MossVoice — единый цикл сборки и тестов (prod = docker).
#
#   make build      собрать production-образ mossvoice/backend:latest
#   make test       собрать + автотесты ВНУТРИ контейнера (офлайн-сьют)
#   make test-live  автотесты + HTTP-интеграция с live TTS-демоном в compose
#   make up         поднять прод-стек (voice/answers/telephony)
#   make stop       остановить прод-стек
#
# Главное правило: тесты идут в том же образе, что и прод. Никакого
# "локального питона с отдельными зависимостями".

IMG      ?= mossvoice/backend:latest
COMPOSE  ?= docker compose -f docker/docker-compose.yml

.PHONY: build test test-live up stop logs clean

build:
	docker build -f docker/Dockerfile -t $(IMG) .

test: build
	$(COMPOSE) --profile tests run --rm tests

test-live: build
	MOSSTEST_TTS=http://voice:9600 MOSSTEST_WAIT_DAEMON=1 \
		$(COMPOSE) --profile tests up -d voice
	MOSSTEST_TTS=http://voice:9600 MOSSTEST_WAIT_DAEMON=1 \
		$(COMPOSE) --profile tests run --rm \
		-e MOSSTEST_TTS=http://voice:9600 -e MOSSTEST_WAIT_DAEMON=1 tests; st=$$?; \
		$(COMPOSE) --profile tests stop voice; \
		$(COMPOSE) --profile tests rm -f voice; \
		exit $$st

up:
	$(COMPOSE) up -d --build

stop:
	$(COMPOSE) stop

logs:
	$(COMPOSE) logs --tail=200 -f

clean:
	$(COMPOSE) down -v --remove-orphans
