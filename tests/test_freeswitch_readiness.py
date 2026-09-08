"""FreeSWITCH readiness parsing."""

from packages.telephony.freeswitch_readiness import (
    FreeSwitchNotReadyReason,
    parse_module_exists,
    parse_status_up,
)


def test_parse_module_exists_true() -> None:
    assert parse_module_exists("true\n", "mod_audio_stream") is True


def test_parse_module_exists_false() -> None:
    assert parse_module_exists("-false\n", "mod_audio_stream") is False


def test_parse_status_up() -> None:
    assert parse_status_up("UP 0 years, 0 days, 0 hours, 1 minute, 5 seconds") is True


def test_not_ready_reason_enum() -> None:
    assert FreeSwitchNotReadyReason.MOD_AUDIO_STREAM_MISSING == "MOD_AUDIO_STREAM_MISSING"
