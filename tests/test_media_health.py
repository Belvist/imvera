"""MediaHealth — answer_wait gated on transport health (ADR-010)."""

from packages.voice_runtime.media_health import MediaHealth, MediaHealthTracker


def test_answer_wait_blocked_on_rtp_stall() -> None:
    t = MediaHealthTracker(rtp_stall_s=2.0)
    t.note_rtp_rx(10, now=0.0)
    t.set_waiting_for_answer(True, now=0.0)
    assert t.evaluate(now=1.0) == MediaHealth.HEALTHY
    assert t.evaluate(now=3.0) == MediaHealth.RTP_STALLED
    assert not t.is_answer_wait_allowed(now=3.0)


def test_pipeline_drop_detected() -> None:
    t = MediaHealthTracker()
    t.note_capture_frame(640, 500.0, now=0.0)
    assert t.evaluate(now=0.1) == MediaHealth.PIPELINE_DROP


def test_remote_silence_during_answer_wait() -> None:
    t = MediaHealthTracker(remote_silence_s=3.0)
    t.note_capture_frame(640, 0.0, now=0.0)
    t.note_actor_frame(640, 0.0, now=0.0)
    t.set_waiting_for_answer(True, now=0.0)
    assert t.evaluate(now=2.0) == MediaHealth.HEALTHY
    assert t.evaluate(now=4.0) == MediaHealth.REMOTE_SILENCE


def test_counters_trace_dict() -> None:
    t = MediaHealthTracker()
    t.note_capture_frame(320, 1200.0, now=1.0)
    t.note_actor_frame(320, 1100.0, now=1.0)
    d = t.counters.to_trace_dict()
    assert d["capture_ws_frames"] == 1
    assert d["actor_pcm_frames"] == 1
