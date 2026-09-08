"""Telnyx media chunk reorder buffer tests."""

from packages.telephony.telnyx_reorder import TelnyxMediaReorderBuffer


def test_reorder_1_3_2_4() -> None:
    buf = TelnyxMediaReorderBuffer()
    out: list[int] = []
    for chunk in (1, 3, 2, 4):
        for c, _ in buf.push(chunk, f"p{chunk}"):
            out.append(c)
    assert out == [1, 2, 3, 4]
    assert buf.counters.telnyx_media_reordered >= 1


def test_duplicate_chunk_delivered_once() -> None:
    buf = TelnyxMediaReorderBuffer()
    first = buf.push(1, "a")
    second = buf.push(1, "a")
    assert len(first) == 1
    assert second == []
    assert buf.counters.telnyx_media_duplicates == 1


def test_missing_chunk_increments_gap_and_advances() -> None:
    buf = TelnyxMediaReorderBuffer(max_gap_skip=1)
    buf.push(1, "a")
    delivered = buf.push(4, "d")
    assert delivered == [(4, "d")]
    assert buf.counters.telnyx_media_gaps >= 1


def test_late_chunk_dropped() -> None:
    buf = TelnyxMediaReorderBuffer()
    buf.push(2, "b")
    late = buf.push(1, "a")
    assert late == []
    assert buf.counters.telnyx_media_late == 1
