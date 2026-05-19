"""Smoke tests for :mod:`atorch_ble._reassembler`.

These cover the headline behaviors of the algorithm. Exhaustive
acceptance-criteria coverage lives in the parser unit-tests ticket.
"""

from __future__ import annotations

from atorch_ble._reassembler import FRAME_SIZE, MAX_BUFFER, FrameReassembler


def _make_frame(packet_type: int = 0x03, fill: int = 0x00) -> bytes:
    """Build a synthetic 36-byte frame with valid magic and direction."""

    body = bytes([fill]) * (FRAME_SIZE - 4)
    return b"\xff\x55\x01" + bytes([packet_type]) + body


def test_clean_single_frame_yields_once() -> None:
    r = FrameReassembler()
    frame = _make_frame()
    out = list(r.feed(frame))
    assert out == [frame]


def test_split_23_plus_19() -> None:
    r = FrameReassembler()
    frame = _make_frame()
    first = list(r.feed(frame[:23]))
    second = list(r.feed(frame[23:]))
    assert first == []
    assert second == [frame]


def test_byte_by_byte_feed() -> None:
    r = FrameReassembler()
    frame = _make_frame(packet_type=0x04, fill=0xAB)
    collected: list[bytes] = []
    for i, byte_val in enumerate(frame):
        out = list(r.feed(bytes([byte_val])))
        if i < FRAME_SIZE - 1:
            assert out == [], f"unexpected emission at byte {i}"
        else:
            collected.extend(out)
    assert collected == [frame]


def test_garbage_prefix_recovery() -> None:
    r = FrameReassembler()
    frame = _make_frame(fill=0x11)
    out = list(r.feed(b"\x00\x11\x22" + frame))
    assert out == [frame]


def test_two_back_to_back_frames() -> None:
    r = FrameReassembler()
    a = _make_frame(packet_type=0x03, fill=0x10)
    b = _make_frame(packet_type=0x04, fill=0x20)
    out = list(r.feed(a + b))
    assert out == [a, b]


def test_overflow_does_not_crash_and_recovers() -> None:
    r = FrameReassembler()
    junk = b"\x00" * 200
    out = list(r.feed(junk))
    assert out == []
    # Internal buffer must stay within cap.
    assert len(r._buf) <= MAX_BUFFER

    frame = _make_frame(fill=0x55)
    out = list(r.feed(frame))
    assert out == [frame]


def test_implausible_direction_is_dropped() -> None:
    r = FrameReassembler()
    bad = b"\xff\x55\x02" + b"\x00" * (FRAME_SIZE - 3)
    good = _make_frame(fill=0x7F)
    out = list(r.feed(bad + good))
    assert out == [good]


def test_inner_magic_in_payload_is_not_a_new_header() -> None:
    r = FrameReassembler()
    # Embed FF 55 inside the body of a valid frame.
    body = bytearray(b"\x00" * (FRAME_SIZE - 4))
    body[10] = 0xFF
    body[11] = 0x55
    frame = b"\xff\x55\x01\x03" + bytes(body)
    assert len(frame) == FRAME_SIZE
    out = list(r.feed(frame))
    assert out == [frame]
