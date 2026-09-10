# IMVERA VoiseUp — CLI contract (ADR-008 §16)

COMPOSE = docker compose -f docker/docker-compose.yml --env-file docker/.env.example
VOICE_COMPOSE = docker compose -f docker/docker-compose.voice.yml
PYTHON = python3
export PYTHONPATH := .

.PHONY: install test lint up down ps logs api-health contracts-check migrate doctor
.PHONY: models-prepare models-up voice-setup voice-up voice-doctor voice-down zoiper-info zoiper-fix voice-e2e voice-sip-e2e
.PHONY: voice-refs-prepare tts-preview tts-preview-list tts-preview-compare
.PHONY: voice-open test-contracts test-dialogue-e2e test-persistence-e2e test-voice test-sip
.PHONY: test-pstn trace-bench test-isolation release-check test-corpus-1k dialogue-corpus-gate effect-delivery-chaos-gate stress-gate stress-gate-100
.PHONY: live-call-1 live-call-soak blackbox-write-catalog blackbox-synthesize-vera live-debug-1 live-daily-check-100
.PHONY: test-dialogue-topic lint-dialogue-topic forensic-gate test-dialogue-rich
.PHONY: test-dialogue-runtime lint-dialogue lint-touched test-semantic-kernel benchmark-semantic-kernel test-voice-perception test-live-replays preflight-gates

install:
	$(PYTHON) -m pip install -e ".[dev,api,mlx,gigaam-stt]"

test:
	$(PYTHON) -m pytest tests/ -q

test-dialogue-topic:
	@echo "GATE: Phase 1 topic correctness (unit + regression + forensic dialogue policy)"
	$(PYTHON) -m pytest tests/test_topic_tracker.py tests/test_topic_live_regression.py \
		tests/test_check_path.py tests/test_dialogue_engine_regression.py \
		tests/test_forensic_gate.py -q

test-dialogue-rich:
	@echo "GATE: Phase 2 rich turn + IssueEpisode correctness"
	$(PYTHON) -m pytest tests/test_rich_turn_understanding.py tests/test_issue_memory.py \
		tests/test_conversation_policy.py tests/test_dialogue_free_speech_regression.py \
		tests/test_evidence_invariant.py tests/test_rich_controls.py \
		tests/test_issue_episode_resume.py tests/test_topic_live_regression.py -q

test-dialogue-runtime:
	@echo "GATE: CallActor rich path + LLM worker contract"
	$(PYTHON) -m pytest tests/test_call_actor_rich_path.py tests/test_llm_worker_contract.py \
		tests/test_call_actor_deferred_delivery.py tests/test_call_actor_llm_fallback.py -q

test-semantic-kernel:
	@echo "GATE: Semantic Kernel adversarial corpus + invariants"
	$(PYTHON) -m pytest tests/test_semantic_kernel.py -q

test-voice-perception:
	@echo "GATE: Post-STT admission, text echo metrics, fragment hold/merge"
	$(PYTHON) -m pytest tests/test_post_stt_gate.py tests/test_voice_perception.py \
		tests/test_call_actor_post_stt.py \
		tests/test_uplink_preroll.py::test_assistant_echo_discarded \
		tests/test_uplink_preroll.py::test_wellness_answers_never_echo_discarded -q

test-live-replays:
	@echo "GATE: live call trace replay corpus (all fixtures)"
	$(PYTHON) -m pytest tests/live_replay/test_corpus.py \
		tests/live_replay/test_fs_1f6d3000.py \
		tests/test_live_path_simplification.py -q

preflight-gates:
	$(PYTHON) scripts/preflight_gates.py

benchmark-semantic-kernel:
	$(PYTHON) scripts/benchmark_semantic_kernel.py

lint-dialogue:
	$(PYTHON) -m ruff check packages/dialogue_engine packages/dialogue/session.py \
		packages/voice_runtime/call_actor.py packages/voice_perception packages/contracts/semantic.py \
		services/llm/worker.py services/llm/prompts.py services/llm/http_provider.py \
		tests/test_rich_turn_understanding.py tests/test_issue_memory.py \
		tests/test_conversation_policy.py tests/test_dialogue_free_speech_regression.py \
		tests/test_evidence_invariant.py tests/test_rich_controls.py \
		tests/test_issue_episode_resume.py tests/test_call_actor_rich_path.py \
		tests/test_llm_worker_contract.py tests/test_free_speech_corpus.py \
		tests/test_semantic_kernel.py tests/test_post_stt_gate.py \
		tests/test_call_actor_post_stt.py scripts/benchmark_semantic_kernel.py

lint-touched:
	@files=$$(git diff --name-only origin/main...HEAD 2>/dev/null | grep '\.py$$' || true); \
	if [ -z "$$files" ]; then \
	  files=$$(git diff --name-only HEAD 2>/dev/null | grep '\.py$$' || true); \
	fi; \
	if [ -z "$$files" ]; then echo "lint-touched: no Python files changed"; exit 0; fi; \
	echo "lint-touched: $$files"; \
	$(PYTHON) -m ruff check $$files

lint-dialogue-topic:
	$(PYTHON) -m ruff check \
		packages/dialogue_engine/topic_tracker.py \
		packages/dialogue_engine/reducer.py \
		packages/dialogue_engine/state.py \
		packages/dialogue_engine/questions.py \
		packages/dialogue_engine/invariants.py \
		packages/dialogue_engine/scenario_runner.py \
		tests/test_topic_tracker.py \
		tests/test_topic_live_regression.py \
		tools/voice_lab/dialogue_forensic.py

forensic-gate:
	@test -n "$(CALL_ID)" || (echo "Usage: make forensic-gate CALL_ID=fs-<id>" && exit 1)
	$(PYTHON) scripts/forensic_gate.py $(CALL_ID)

test-corpus-1k:
	@echo "LAYER: CallSession dialogue corpus (NOT live SIP×1000)"
	$(PYTHON) scripts/run_dialogue_corpus.py --workers 4 --minimum 1000
	$(PYTHON) -m pytest tests/corpus/test_call_actor_load.py -q

dialogue-corpus-gate:
	@echo "LAYER: DialogueEngine >=500 full daily-check FSM trajectories"
	$(PYTHON) scripts/dialogue_corpus_gate.py
	$(PYTHON) -m pytest tests/test_dialogue_corpus_gate.py -q

effect-delivery-chaos-gate:
	@echo "LAYER: Effect Delivery V2 outbox lifecycle chaos"
	$(PYTHON) -m pytest tests/test_effect_delivery_v2.py tests/test_engine_effect_delivery.py -q

stress-gate:
	@echo "LAYER: stress gate — IMVERA_STRESS_COUNT=$${IMVERA_STRESS_COUNT:-100} scenarios, JSONL in .run/stress_gate/"
	$(PYTHON) scripts/stress_gate.py --count $${IMVERA_STRESS_COUNT:-100}

stress-gate-100:
	@echo "LAYER: 100-scenario stress (engine + call_actor + session), full JSONL logging"
	$(PYTHON) scripts/stress_gate.py --count 100 --workers 8 --concurrency 4

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
	$(PYTHON) scripts/prepare_voice_refs.py

voice-refs-prepare:
	$(PYTHON) scripts/prepare_voice_refs.py

tts-preview-list:
	$(PYTHON) scripts/tts_preview.py --list-refs

tts-preview:
	$(PYTHON) scripts/tts_preview.py --out /tmp/imvera_tts_preview.wav

tts-preview-compare:
	$(PYTHON) scripts/tts_compare.py --out /tmp/imvera_tts_compare
	@echo "Open /tmp/imvera_tts_compare/listen.html in a browser"

voice-up:
	$(PYTHON) scripts/voice_up.py

voice-doctor:
	@$(PYTHON) scripts/voice_doctor.py

voice-down:
	$(PYTHON) scripts/voice_down.py

zoiper-info:
	$(PYTHON) scripts/zoiper_info.py

zoiper-fix:
	$(PYTHON) scripts/zoiper_apply_mac.py

voice-e2e:
	@$(PYTHON) scripts/voice_e2e.py

voice-sip-e2e:
	@$(PYTHON) scripts/voice_sip_e2e.py

voice-sip-downlink:
	@$(PYTHON) scripts/voice_sip_e2e.py --downlink-only

voice-call-gate:
	@$(PYTHON) scripts/voice_call_gate.py

freeswitch-up:
	@$(PYTHON) scripts/freeswitch_up.py

freeswitch-down:
	@$(PYTHON) scripts/freeswitch_down.py

freeswitch-media-gate:
	@$(PYTHON) scripts/freeswitch_media_gate.py

freeswitch-soak-gate:
	@$(PYTHON) scripts/freeswitch_soak_gate.py

freeswitch-synthetic-sip:
	@$(PYTHON) scripts/freeswitch_synthetic_sip_media.py

freeswitch-docker-gate:
	@$(PYTHON) scripts/freeswitch_docker_gate.py

freeswitch-zoiper-info:
	@$(PYTHON) scripts/freeswitch_zoiper_info.py

freeswitch-zoiper-fix:
	@$(PYTHON) scripts/freeswitch_zoiper_apply_mac.py

freeswitch-zoiper-voice-up:
	@$(PYTHON) scripts/freeswitch_zoiper_voice_up.py

freeswitch-zoiper-voice-down:
	@$(PYTHON) scripts/freeswitch_zoiper_voice_down.py

perception-up:
	docker compose -f infra/freeswitch/docker-compose.yml up -d --build perception

perception-down:
	docker compose -f infra/freeswitch/docker-compose.yml stop perception

perception-health:
	curl -sf http://127.0.0.1:9110/health/ready | $(PYTHON) -m json.tool

freeswitch-forensic-collect:
	@$(PYTHON) scripts/freeswitch_forensic_collect.py $(UUID) --call-id $(CALL_ID)

freeswitch-readiness:
	@$(PYTHON) scripts/freeswitch_readiness_check.py --wait 120

freeswitch-external-gate:
	@$(PYTHON) scripts/freeswitch_external_gate.py

media-bridge-up:
	@$(PYTHON) services/imvera_media_bridge/main.py

sip-call-diag:
	@IMVERA_WS_DIAG=1 $(PYTHON) scripts/sip_call_diag.py

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

test-dialogue-gates:
	$(PYTHON) -m pytest \
		tests/test_planner_question_ledger.py \
		tests/test_wait_contract.py \
		tests/test_inference_stop_epoch.py \
		tests/test_call_actor_backchannel_ledger.py \
		tests/test_dispatch_failure_matrix.py \
		tests/test_semantic_pipeline.py \
		tests/test_mixed_nonanswer_sequence.py \
		tests/test_mixed_nonanswer_sequence_callactor.py \
		tests/test_complaint_voice_path.py \
		tests/test_call_actor_llm_fallback.py \
		tests/test_dialogue_acceptance_gaps.py \
		-q

test-dialogue-live:
	@$(PYTHON) -m pytest tests/test_llm_live_dialogue.py -v

dialogue-smoke:
	@$(PYTHON) scripts/dialogue_product_smoke.py

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
	@echo "BLOCKED: PSTN trunk — use IMVERA_LIVE_TRANSPORT=pstn make live-call-soak"

live-call-1:
	@echo "LAYER: black-box SIP/RTP E2E — 1 real call via external pyVoIP caller"
	@$(PYTHON) tools/blackbox_caller/main.py --calls 1

live-call-soak:
	@echo "LAYER: black-box SIP/RTP soak — IMVERA_LIVE_CALLS=$${IMVERA_LIVE_CALLS:-10}"
	@$(PYTHON) tools/blackbox_caller/main.py --calls $${IMVERA_LIVE_CALLS:-10}

live-debug-1:
	@echo "LAYER: real SIP full daily-check — 1 call, server trace + DEBUG_REPORT.md"
	@$(PYTHON) scripts/live_daily_check_gate.py --calls 1 --profile full --scenario $${IMVERA_LIVE_DEBUG_SCENARIO:-good-clean_short-00}

live-daily-check-100:
	@echo "LAYER: real SIP full daily-check soak — 100 calls, stop on first fail"
	@$(PYTHON) scripts/live_daily_check_gate.py --calls 100 --profile full --stop-on-fail

internal-docker-live-smoke-1:
	@echo "PHASE A: internal docker live smoke — 1 full daily-check (diagnostic only)"
	@$(PYTHON) scripts/internal_docker_live_smoke_gate.py

internal-docker-live-smoke-10:
	@echo "PHASE A: internal docker live smoke — up to 10 calls (runtime stability)"
	@IMVERA_INTERNAL_DOCKER_CALLS=10 IMVERA_LIVE_DEBUG_STOP_ON_FAIL=0 \
		$(PYTHON) scripts/internal_docker_live_smoke_gate.py

pjsua2-transport-gate:
	@echo "PHASE B: PJSUA2 transport gate — REGISTER/INVITE/RTP/WAV (no dialogue)"
	@$(PYTHON) scripts/pjsua2_transport_gate.py

blackbox-write-catalog:
	@$(PYTHON) tools/blackbox_caller/main.py --write-catalog

blackbox-synthesize-vera:
	@echo "L3-A: synthesize black-box uplink WAV via Vera Silero TTS (NOT human voice bank)"
	@$(PYTHON) scripts/blackbox_synthesize_vera_voice.py

trace-bench:
	@echo "BLOCKED: tools/voice_lab bench harness pending"

test-isolation:
	$(PYTHON) -m pytest tests/test_integrity.py::test_wrong_family_cannot_read -q

release-check:
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) doctor
