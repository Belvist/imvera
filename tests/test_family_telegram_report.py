"""Telegram family report renders truthfully (no DB needed)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tools.family_notify.telegram_report import build_message

pytestmark = pytest.mark.dialogue_engine


@pytest.fixture(autouse=True)
def isolated_demo_ledger(monkeypatch, tmp_path):
    from tools.family_notify import telegram_report

    monkeypatch.setattr(telegram_report, "SENT_FILE", tmp_path / "sent.json")


def _snap(**kw):
    base = {
        "outcomes": {},
        "metadata": {},
        "facts": {},
        "observations": [],
        "call_ended": True,
    }
    base.update(kw)
    return SimpleNamespace(model_dump=lambda mode="json": base)


def test_technical_call_says_partial() -> None:
    msg = build_message(
        "fs-x",
        _snap(outcomes={"candidate_family_status": "UNSET", "call_outcome": "TECHNICAL"}),
    )
    assert "технической" in msg
    assert "Нет данных" in msg


def test_yellow_shows_concern_and_facts() -> None:
    msg = build_message(
        "fs-x",
        _snap(
            outcomes={"candidate_family_status": "YELLOW"},
            metadata={"elder_display_name": "Тест", "wellness_concern": "болит голова"},
            facts={"mood": "нормальное"},
            call_ended=True,
        ),
    )
    assert "Нужно внимание" in msg
    assert "болит голова" in msg
    assert "Настроение: нормальное" in msg


@pytest.mark.parametrize("outcome,ended", [("TECHNICAL", True), ("NO_CONTACT", True), ("", False)])
def test_incomplete_call_cannot_display_green(outcome, ended):
    msg = build_message(
        "fs-x", _snap(outcomes={"candidate_family_status": "GREEN", "call_outcome": outcome},
                      call_ended=ended),
    )
    assert "🟢" not in msg and "Всё хорошо" not in msg
    assert "Нет данных" in msg


def test_incomplete_call_does_not_hide_reported_urgent_signal():
    msg = build_message(
        "fs-x", _snap(outcomes={"candidate_family_status": "RED", "call_outcome": "TECHNICAL"}),
    )
    assert "Тревога" in msg and "технической" in msg


def test_failed_demo_send_does_not_log_token_or_chat(monkeypatch, capsys):
    from tools.family_notify import telegram_report

    monkeypatch.setenv("IMVERA_TG_BOT_TOKEN", "test-secret-token")
    monkeypatch.setenv("IMVERA_TG_CHAT_ID", "test-private-chat")
    monkeypatch.setattr(telegram_report, "_snapshot", lambda _: _snap())

    def fail(*args, **kwargs):
        raise RuntimeError("https://api.telegram.org/bottest-secret-token test-private-chat")

    monkeypatch.setattr(telegram_report, "send_message", fail)
    assert not telegram_report.report_call("test-call", dry_run=False)
    output = capsys.readouterr().out
    assert "RuntimeError" in output
    assert "test-secret-token" not in output and "test-private-chat" not in output


def test_partial_acceptance_retries_only_the_failed_recipient(monkeypatch):
    from tools.family_notify import telegram_report as reporter

    monkeypatch.setenv("IMVERA_TG_BOT_TOKEN", "fake")
    monkeypatch.setenv("IMVERA_TG_CHAT_ID", "a,a,b")
    monkeypatch.setattr(reporter, "_snapshot", lambda _: _snap())
    calls = []

    def send(token, chat_id, text):
        calls.append(chat_id)
        if calls == ["a", "b"]:
            raise RuntimeError("synthetic rejection")

    monkeypatch.setattr(reporter, "send_message", send)
    assert not reporter.report_call("partial", dry_run=False)
    assert "partial" not in reporter._load_sent()
    assert reporter.report_call("partial", dry_run=False)
    assert reporter.report_call("partial", dry_run=False)
    assert calls == ["a", "b", "b"]
    assert "partial" in reporter._load_sent()


def test_corrupt_ledger_blocks_sending_instead_of_forgetting_receipts(monkeypatch):
    from tools.family_notify import telegram_report as reporter

    monkeypatch.setenv("IMVERA_TG_BOT_TOKEN", "fake")
    monkeypatch.setenv("IMVERA_TG_CHAT_ID", "a")
    monkeypatch.setattr(reporter, "_snapshot", lambda _: _snap())
    calls = []
    monkeypatch.setattr(reporter, "send_message", lambda *a: calls.append(a))
    reporter.SENT_FILE.write_text("{corrupt")
    with pytest.raises(ValueError):
        reporter.report_call("corrupt", dry_run=False)
    assert not calls


def test_dry_run_cannot_claim_acceptance_in_the_persistent_ledger(monkeypatch):
    from tools.family_notify import telegram_report as reporter

    monkeypatch.setattr(reporter, "_snapshot", lambda _: _snap())
    monkeypatch.setattr(reporter, "send_message", lambda *a: pytest.fail("dry run must not send"))
    assert reporter.report_call("preview", dry_run=True)
    assert not reporter.SENT_FILE.exists()


def test_concurrent_demo_reporters_share_recipient_receipts(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from tools.family_notify import telegram_report as reporter

    monkeypatch.setenv("IMVERA_TG_BOT_TOKEN", "fake")
    monkeypatch.setenv("IMVERA_TG_CHAT_ID", "a")
    monkeypatch.setattr(reporter, "_snapshot", lambda _: _snap())
    entered, release = Event(), Event()
    calls = []

    def send(*args):
        calls.append(args)
        entered.set()
        assert release.wait(2)

    monkeypatch.setattr(reporter, "send_message", send)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(reporter.report_call, "concurrent", dry_run=False)
        assert entered.wait(2)
        second = pool.submit(reporter.report_call, "concurrent", dry_run=False)
        release.set()
        assert first.result(timeout=2) and second.result(timeout=2)
    assert len(calls) == 1


def test_watcher_preserves_partial_receipts_across_polls(monkeypatch):
    from tools.family_notify import telegram_report as reporter

    monkeypatch.setenv("IMVERA_TG_BOT_TOKEN", "fake")
    monkeypatch.setenv("IMVERA_TG_CHAT_ID", "a,b")
    monkeypatch.setattr(reporter, "_snapshot", lambda _: _snap())
    monkeypatch.setattr(reporter, "recent_ended_calls", lambda **kw: ["watched"])
    calls, ticks = [], []

    def send(token, chat_id, text):
        calls.append(chat_id)
        if calls == ["a", "b"]:
            raise RuntimeError("synthetic rejection")

    def tick(*args):
        ticks.append(1)
        if len(ticks) == 3:
            raise SystemExit

    monkeypatch.setattr(reporter, "send_message", send)
    monkeypatch.setattr(reporter.time, "sleep", tick)
    with pytest.raises(SystemExit):
        reporter.watch(0, False, 24)
    assert calls == ["a", "b", "b"]
    assert "watched" in reporter._load_sent()
