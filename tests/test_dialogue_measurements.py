"""Decision evidence must not become invented phone/model/quality measurements."""

from __future__ import annotations

from copy import deepcopy

import pytest

from tools.voice_lab.dialogue_comparison import measure_capture, run_imvera


@pytest.fixture
def suite():
    return {
        "version": "measure-test", "language": "ru", "speech_day": "0", "speech_hour": "10",
        "elder_display_name": "Тамара Юрьевна", "missions": {},
        "cases": [
            {"id": "facts", "mission": "daily", "inputs": [
                "Самочувствие хорошее, настроение спокойное, спала хорошо, сегодня пойду гулять.",
                "Нет, больше ничего.", "До свидания.",
            ]},
            {"id": "story", "mission": "daily", "inputs": [
                "Внучка приезжала, хорошо посидели.", "Чай пили, разговаривали.",
                "Вспоминали наши поездки.",
            ]},
        ],
    }


@pytest.fixture
def capture(monkeypatch, suite):
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "legacy")
    return run_imvera(suite, "suite-test-sha", "SDK-observer", decision_metadata=True)


def test_observer_preserves_real_sdk_speech_and_mission_outcomes(monkeypatch, suite):
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "legacy")
    ordinary = run_imvera(suite, "suite-test-sha", "ordinary")
    observed = run_imvera(suite, "suite-test-sha", "observed", decision_metadata=True)
    for before, after in zip(ordinary["cases"], observed["cases"], strict=True):
        assert [t["assistant"] for t in before["turns"]] == [
            t["assistant"] for t in after["turns"]
        ]
        assert before["mission_result"] == after["mission_result"]
        assert before["outcomes"] == after["outcomes"]


def test_shadow_still_preserves_sdk_output_and_reports_authority(monkeypatch, suite, capture):
    monkeypatch.setenv("IMVERA_ACTION_POLICY_MODE", "shadow")
    shadow = run_imvera(suite, "suite-test-sha", "shadow", decision_metadata=True)
    assert shadow["runtime"]["router"]["action_policy.mode"] == "shadow"
    for a, b in zip(capture["cases"], shadow["cases"], strict=True):
        assert [t["assistant"] for t in a["turns"]] == [t["assistant"] for t in b["turns"]]
        stats = b["turns"][-1]["state_after"]["router_stats"]
        assert stats.get("legacy_invocations", 0) > 0
        assert not stats.get("policy_authoritative", 0)


def test_multi_fact_metrics_read_accepted_state_not_sentence_count(capture):
    report = measure_capture(capture)
    assert report["cases"][0]["max_newly_filled_slots_per_user_turn"] == 4
    assert report["cases"][0]["final_state"]["slots"]["wellness"] == "FILLED"
    for case in capture["cases"]:
        for turn in case["turns"]:
            for decision in turn["decisions"]:
                fx = decision["effect"]
                if fx["marks_question"]:
                    delivered = decision["after_delivery"]["delivered_question"]
                    assert delivered and delivered["question_id"] == fx["question_id"]


def test_question_marks_in_nonquestion_speech_do_not_create_asks(capture):
    changed = deepcopy(capture)
    modified = 0
    for case in changed["cases"]:
        for turn in case["turns"]:
            for index, decision in enumerate(turn["decisions"]):
                if not decision["effect"]["marks_question"]:
                    decision["effect"]["text"] += " Вы спрашивали «Как дела?»"
                    turn["assistant"][index] = decision["effect"]["text"]
                    modified += 1
    assert modified
    assert measure_capture(capture)["cases"] == measure_capture(changed)["cases"]


def test_same_question_representation_is_not_another_distinct_question(capture):
    changed = deepcopy(capture)
    changed["cases"][0]["turns"][0]["decisions"].append(
        deepcopy(changed["cases"][0]["turns"][0]["decisions"][0])
    )
    opening = changed["cases"][0]["turns"][0]
    opening["assistant"].append(opening["assistant"][0])
    opening["intents"].append(opening["intents"][0])
    before = measure_capture(capture)["cases"][0]["counts"]
    after = measure_capture(changed)["cases"][0]["counts"]
    assert after["distinct_question_ids"] == before["distinct_question_ids"]
    assert after["same_question_identity_representations"] == 1


def test_planned_only_or_telephone_claim_cannot_be_measured_as_sdk_delivery(capture):
    changed = deepcopy(capture)
    changed["cases"][0]["turns"][0]["decisions"][0]["delivery"] = "PLANNED"
    with pytest.raises(ValueError, match="real delivery"):
        measure_capture(changed)
    capture["provider"]["channel"] = "telephone"
    with pytest.raises(ValueError, match="text capture"):
        measure_capture(capture)


def test_text_only_capture_cannot_invent_missing_state_or_models(capture):
    report = measure_capture(capture)
    assert set(report["not_measured"].values()) == {"NOT_RUN"}
    del capture["cases"][0]["turns"][0]["decisions"]
    with pytest.raises(ValueError, match="decision/state"):
        measure_capture(capture)


def test_missing_source_and_audio_modality_stay_explicit(capture):
    capture["cases"][0]["required_modalities"] = ["phone_audio", "interruption"]
    report = measure_capture(capture)
    assert report["cases"][0]["required_modalities"] == ["phone_audio", "interruption"]
    assert report["cases"][0]["phone_acceptance"] == "NOT_RUN"
    capture["runtime"].pop("source_sha256")
    with pytest.raises(ValueError, match="source fingerprints"):
        measure_capture(capture)


def test_real_thread_return_and_replay_preset_are_observed(capture):
    report = measure_capture(capture)
    story = report["cases"][1]
    assert story["counts"]["budget_to_wellness_return_proxy"] == 1
    assert story["replay_configuration"]["mandatory_background_goals"] is True
    assert "coverage_ladder_enabled" in report["runtime"]


@pytest.mark.parametrize("mismatch", ["delivered", "transcript", "question_type", "generation"])
def test_contradictory_capture_cannot_produce_delivery_counts(capture, mismatch):
    opening = capture["cases"][0]["turns"][0]
    decision = opening["decisions"][0]
    if mismatch == "delivered":
        decision["after_delivery"]["delivered_question"] = None
    elif mismatch == "transcript":
        opening["assistant"] = []
    elif mismatch == "question_type":
        decision["effect"]["marks_question"] = "yes"
    else:
        decision["effect"]["generation"] += 1
    with pytest.raises(ValueError):
        measure_capture(capture)


@pytest.mark.parametrize("elapsed", [True, -1, float("nan"), "fast"])
def test_bad_elapsed_values_cannot_become_latency_measurements(capture, elapsed):
    capture["cases"][0]["turns"][1]["text_processing_ms"] = elapsed
    with pytest.raises(ValueError, match="Invalid SDK elapsed"):
        measure_capture(capture)
