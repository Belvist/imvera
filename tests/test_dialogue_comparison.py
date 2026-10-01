"""Keep comparison evidence honest when an external capture is unavailable."""

from __future__ import annotations

from copy import deepcopy

import pytest

from tools.voice_lab.dialogue_comparison import (
    FORMAT,
    compare_captures,
    validate_capture,
)


def fixture() -> tuple[dict, dict]:
    suite = {
        "version": "test",
        "language": "ru",
        "cases": [
            {"id": "a", "inputs": ["Не помню."]},
            {"id": "b", "inputs": ["Нет."]},
        ],
    }
    capture = {
        "format": FORMAT,
        "suite_sha256": "test-sha",
        "provider": {
            "name": "test-provider",
            "version": "v1",
            "channel": "text",
            "language": "ru",
            "captured_at": "2026-10-01T00:00:00Z",
            "evidence_ref": "test fixture, not a competitor measurement",
        },
        "cases": [
            {
                "id": "a",
                "turns": [
                    {"user": None, "assistant": ["Когда это началось?"]},
                    {"user": "Не помню.", "assistant": ["Не будем угадывать."]},
                ],
            }
        ],
    }
    return suite, capture


def test_empty_capture_cannot_be_presented_as_measured() -> None:
    suite, capture = fixture()
    capture["cases"] = []
    with pytest.raises(ValueError, match="NOT_RUN"):
        validate_capture(capture, suite, "test-sha")


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("evidence_ref", "", "evidence_ref"),
        ("language", "en", "Different language"),
    ],
)
def test_unattributable_or_translated_capture_is_rejected(
    field: str, value: str, match: str
) -> None:
    suite, capture = fixture()
    capture["provider"][field] = value
    with pytest.raises(ValueError, match=match):
        validate_capture(capture, suite, "test-sha")


def test_missing_or_changed_input_cannot_make_an_easier_comparison() -> None:
    suite, capture = fixture()
    capture["cases"][0]["turns"][1]["user"] = "Сегодня."
    with pytest.raises(ValueError, match="Changed or missing inputs"):
        validate_capture(capture, suite, "test-sha")


def test_text_cannot_be_ranked_against_a_telephone_capture() -> None:
    suite, capture = fixture()
    phone = deepcopy(capture)
    phone["provider"]["channel"] = "telephone"
    with pytest.raises(ValueError, match="Different channels"):
        compare_captures(capture, phone, suite, "test-sha")


def test_partial_comparison_keeps_missing_case_and_human_rating_visible() -> None:
    suite, capture = fixture()
    report = compare_captures(capture, deepcopy(capture), suite, "test-sha")
    assert "1/2" in report
    assert "## b" in report and "NOT_RUN" in report
    assert "not a measured superiority" in report
    assert "Human review" in report
