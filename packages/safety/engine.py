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


def _at_least(level: RiskLevel, minimum: RiskLevel) -> bool:
    return _ORDER[level] >= _ORDER[minimum]


def _level_from_deterministic(signals: list[str]) -> RiskLevel:
    level = RiskLevel.NONE
    for sid in signals:
        rl = signal_to_risk_level(sid)
        level = _max_level(level, RiskLevel.RED if rl == "RED" else RiskLevel.YELLOW)
    return level


def _level_from_semantic(semantic_signals: list[str]) -> RiskLevel:
    if not semantic_signals:
        return RiskLevel.NONE
    return RiskLevel.POSSIBLE


def _recompute_active_risk(safety: SafetySnapshot) -> RiskLevel:
    level = RiskLevel.NONE
    for episode_id, ep_level in safety.episode_levels.items():
        if episode_id in safety.dismissed_episode_ids:
            continue
        level = _max_level(level, ep_level)
    return level


def _register_episode(safety: SafetySnapshot, level: RiskLevel) -> None:
    safety.episode_seq += 1
    episode_id = f"ep-{safety.episode_seq}"
    safety.active_episode_id = episode_id
    safety.episode_levels[episode_id] = level
    safety.active_risk = _recompute_active_risk(safety)
    safety.signal_resolution = SignalResolution.UNRESOLVED


class SafetyEngine:
    """Merge deterministic + semantic signals. Deterministic rules own RED."""

    @staticmethod
    def ingest_transcript(
        safety: SafetySnapshot,
        text: str,
        semantic_signals: list[str] | None = None,
        *,
        allow_new_episodes: bool = True,
    ) -> SafetySnapshot:
        if not allow_new_episodes:
            return safety
        signals = match_deterministic_signals(text)
        level = _level_from_deterministic(signals)

        if semantic_signals:
            sem_level = _level_from_semantic(semantic_signals)
            level = _max_level(level, sem_level)

        safety.highest_signal_seen = _max_level(safety.highest_signal_seen, level)

        if signals and _at_least(level, RiskLevel.YELLOW):
            _register_episode(safety, level)
        elif semantic_signals and level == RiskLevel.POSSIBLE:
            _register_episode(safety, RiskLevel.POSSIBLE)
        elif level > RiskLevel.NONE:
            safety.active_risk = _max_level(safety.active_risk, level)

        return safety

    @staticmethod
    def confirm_red(safety: SafetySnapshot) -> SafetySnapshot:
        safety.signal_resolution = SignalResolution.CONFIRMED
        safety.highest_signal_seen = RiskLevel.RED
        if safety.active_episode_id:
            safety.episode_levels[safety.active_episode_id] = RiskLevel.RED
        else:
            _register_episode(safety, RiskLevel.RED)
        safety.active_risk = _recompute_active_risk(safety)
        return safety

    @staticmethod
    def resolve_false_alarm(
        safety: SafetySnapshot,
        episode_id: str | None = None,
    ) -> SafetySnapshot:
        """Dismiss one episode only; other episodes (incl. POSSIBLE) remain active."""
        ep = episode_id or safety.active_episode_id
        if ep and ep not in safety.dismissed_episode_ids:
            safety.dismissed_episode_ids.append(ep)
        safety.active_risk = _recompute_active_risk(safety)
        if safety.active_risk == RiskLevel.NONE:
            safety.signal_resolution = SignalResolution.CONFIRMED_FALSE_ALARM
        else:
            safety.signal_resolution = SignalResolution.UNRESOLVED
        return safety
