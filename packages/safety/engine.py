"""SafetyEngine — monotonic merge of risk signals."""

from packages.contracts.enums import RiskLevel, SignalResolution
from packages.contracts.status import SafetySnapshot
from packages.safety.rules import match_deterministic_signals, signal_to_risk_level

_ORDER = {
    RiskLevel.NONE: 0,
    RiskLevel.POSSIBLE: 1,
    RiskLevel.YELLOW: 2,
    RiskLevel.RED: 3,
}


def _max_level(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _ORDER[a] >= _ORDER[b] else b


class SafetyEngine:
    """Merge deterministic + semantic signals. No LLM authority."""

    @staticmethod
    def ingest_transcript(
        safety: SafetySnapshot,
        text: str,
        semantic_signals: list[str] | None = None,
    ) -> SafetySnapshot:
        signals = match_deterministic_signals(text)
        level = RiskLevel.NONE
        for sid in signals:
            rl = signal_to_risk_level(sid)
            level = _max_level(level, RiskLevel.RED if rl == "RED" else RiskLevel.YELLOW)

        if semantic_signals:
            for sig in semantic_signals:
                if "red" in sig.lower() or "fall" in sig.lower():
                    level = _max_level(level, RiskLevel.RED)
                elif "concern" in sig.lower() or "yellow" in sig.lower():
                    level = _max_level(level, RiskLevel.YELLOW)
                elif "possible" in sig.lower():
                    level = _max_level(level, RiskLevel.POSSIBLE)

        safety.highest_signal_seen = _max_level(safety.highest_signal_seen, level)
        if safety.signal_resolution != SignalResolution.CONFIRMED_FALSE_ALARM:
            safety.active_risk = _max_level(safety.active_risk, level)
        return safety

    @staticmethod
    def confirm_red(safety: SafetySnapshot) -> SafetySnapshot:
        safety.signal_resolution = SignalResolution.CONFIRMED
        safety.active_risk = RiskLevel.RED
        safety.highest_signal_seen = RiskLevel.RED
        return safety

    @staticmethod
    def resolve_false_alarm(safety: SafetySnapshot) -> SafetySnapshot:
        """After deterministic false-alarm protocol (ADR-005)."""
        safety.signal_resolution = SignalResolution.CONFIRMED_FALSE_ALARM
        safety.active_risk = RiskLevel.NONE
        return safety
