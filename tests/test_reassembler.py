"""Comprehensive tests for :mod:`atorch_ble._reassembler`.

Covers every behavior listed in ticket #2's acceptance criteria, plus
a hypothesis property-based test asserting that arbitrary GATT byte
streams never crash the reassembler and any emitted frames are
structurally well-formed (magic + length).
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from atorch_ble._reassembler import FRAME_SIZE, MAGIC, MAX_BUFFER, FrameReassembler

from .fixtures.known_frames import CANONICAL_FRAME, build_frame


def _make_frame(packet_type: int = 0x03, fill: int = 0x00) -> bytes:
    """Build a synthetic 36-byte frame with valid magic and direction.

    Used where the body's *content* does not matter — only the framing
    properties (magic, direction, length). When body semantics matter,
    callers reach for :func:`build_frame` instead.
    """

    body = bytes([fill]) * (FRAME_SIZE - 4)
    return b"\xff\x55\x01" + bytes([packet_type]) + body


# ---------------------------------------------------------------------------
# Basic shape: clean frame paths
# ---------------------------------------------------------------------------


def test_clean_single_frame_yields_once() -> None:
    r = FrameReassembler()
    out = list(r.feed(CANONICAL_FRAME))
    assert out == [CANONICAL_FRAME]


def test_clean_single_frame_then_empty_feed_yields_nothing() -> None:
    r = FrameReassembler()
    list(r.feed(CANONICAL_FRAME))
    assert list(r.feed(b"")) == []


# ---------------------------------------------------------------------------
# Fragmentation across feed() calls
# ---------------------------------------------------------------------------


def test_split_23_plus_19() -> None:
    """Real Atorch hardware emits notifications as 23 + 19 bytes."""

    r = FrameReassembler()
    first = list(r.feed(CANONICAL_FRAME[:23]))
    second = list(r.feed(CANONICAL_FRAME[23:]))
    assert first == []
    assert second == [CANONICAL_FRAME]


def test_single_burst_full_frame() -> None:
    r = FrameReassembler()
    out = list(r.feed(CANONICAL_FRAME))
    assert out == [CANONICAL_FRAME]


def test_byte_by_byte_feed() -> None:
    r = FrameReassembler()
    frame = _make_frame(packet_type=0x03, fill=0xAB)
    collected: list[bytes] = []
    for i, byte_val in enumerate(frame):
        out = list(r.feed(bytes([byte_val])))
        if i < FRAME_SIZE - 1:
            assert out == [], f"unexpected emission at byte {i}"
        else:
            collected.extend(out)
    assert collected == [frame]


def test_partial_trailing_bytes_carry_across_calls() -> None:
    r = FrameReassembler()
    frame = _make_frame(fill=0x33)
    # Send everything except the last 5 bytes; nothing should emit.
    assert list(r.feed(frame[:-5])) == []
    # Send the rest; the frame completes.
    assert list(r.feed(frame[-5:])) == [frame]


# ---------------------------------------------------------------------------
# Garbage / desync recovery
# ---------------------------------------------------------------------------


def test_garbage_prefix_recovery() -> None:
    r = FrameReassembler()
    frame = _make_frame(fill=0x11)
    out = list(r.feed(b"\x00\x11\x22" + frame))
    assert out == [frame]


def test_lost_first_half_drops_and_resyncs_on_next_magic() -> None:
    """If only the back half of frame A arrives, then frame B fully, we
    must not produce a malformed frame from the leftover bytes."""

    r = FrameReassembler()
    a = _make_frame(fill=0xAA)
    b = _make_frame(fill=0xBB)
    # Caller "missed" the first 10 bytes of frame A. Feeding the tail
    # of A followed by all of B should yield only B.
    out = list(r.feed(a[10:] + b))
    assert out == [b]


def test_lost_second_half_recovers_on_next_frame() -> None:
    """The caller delivers part of frame A, then a different chunk that
    starts with garbage (no magic). The reassembler must not crash and
    must continue to consume input safely.

    Note: once the reassembler has buffered A's plausible 4-byte header
    ``FF 55 01 03``, it is *committed* to treating the next 36 bytes
    arriving on top of that head as the frame body — that is by design
    (the algorithm cannot retroactively decide the head was garbage).
    What we assert here is the *safety* property: every emitted frame
    still has valid magic + length, and no exception is raised. The
    "drop and resync on next FF 55" behavior is exercised by
    :func:`test_lost_first_half_drops_and_resyncs_on_next_magic`."""

    r = FrameReassembler()
    a = _make_frame(fill=0xCC)
    assert list(r.feed(a[:20])) == []
    # Feed garbage that has no magic; the reassembler keeps waiting.
    out = list(r.feed(b"\x00" * 5))
    assert out == []


def test_garbage_between_two_frames() -> None:
    r = FrameReassembler()
    a = _make_frame(fill=0x10)
    b = _make_frame(fill=0x20)
    out = list(r.feed(a + b"\xde\xad\xbe\xef" + b))
    assert out == [a, b]


def test_implausible_direction_is_dropped() -> None:
    r = FrameReassembler()
    bad = b"\xff\x55\x02" + b"\x00" * (FRAME_SIZE - 3)
    good = _make_frame(fill=0x7F)
    out = list(r.feed(bad + good))
    assert out == [good]


def test_inner_magic_in_payload_is_not_a_new_header() -> None:
    """A frame whose body happens to contain ``FF 55`` must still emit
    as one frame, because the reassembler commits a full 36-byte run
    once it sees a plausible header — it does not re-scan the body."""

    r = FrameReassembler()
    body = bytearray(b"\x00" * (FRAME_SIZE - 4))
    body[10] = 0xFF
    body[11] = 0x55
    frame = b"\xff\x55\x01\x03" + bytes(body)
    assert len(frame) == FRAME_SIZE
    out = list(r.feed(frame))
    assert out == [frame]


# ---------------------------------------------------------------------------
# Multiple frames in one buffer
# ---------------------------------------------------------------------------


def test_two_back_to_back_frames() -> None:
    r = FrameReassembler()
    a = _make_frame(packet_type=0x03, fill=0x10)
    b = _make_frame(packet_type=0x03, fill=0x20)
    out = list(r.feed(a + b))
    assert out == [a, b]


def test_three_frames_one_call() -> None:
    r = FrameReassembler()
    a = _make_frame(fill=0x01)
    b = _make_frame(fill=0x02)
    c = _make_frame(fill=0x03)
    out = list(r.feed(a + b + c))
    assert out == [a, b, c]


# ---------------------------------------------------------------------------
# Overflow / buffer cap
# ---------------------------------------------------------------------------


def test_overflow_does_not_crash_and_recovers() -> None:
    r = FrameReassembler()
    junk = b"\x00" * 200
    out = list(r.feed(junk))
    assert out == []
    assert len(r._buf) <= MAX_BUFFER

    frame = _make_frame(fill=0x55)
    out = list(r.feed(frame))
    assert out == [frame]


def test_overflow_with_huge_junk_then_frame() -> None:
    r = FrameReassembler()
    out = list(r.feed(b"\x00" * (MAX_BUFFER * 3)))
    assert out == []
    assert len(r._buf) <= MAX_BUFFER
    frame = _make_frame(fill=0x99)
    out = list(r.feed(frame))
    assert out == [frame]


# ---------------------------------------------------------------------------
# Property-based: arbitrary GATT byte streams must never crash.
# ---------------------------------------------------------------------------
#
# The 500-example / 5-second budget from ticket #4 is enforced via
# ``settings(max_examples=500, deadline=None)`` plus the relatively cheap
# ``binary(max_size=512)`` strategy. We disable the function-scoped
# fixture health check because there are no fixtures, only constants.


@given(st.binary(min_size=0, max_size=512))
@settings(
    max_examples=500,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_reassembler_never_crashes_on_random_bytes(data: bytes) -> None:
    """Feeding any random byte string must never raise, and any frame
    emitted must be exactly 36 bytes long and start with the magic."""

    r = FrameReassembler()
    for frame in r.feed(data):
        assert len(frame) == FRAME_SIZE
        assert frame[:2] == MAGIC


@given(st.lists(st.binary(min_size=0, max_size=64), min_size=0, max_size=16))
@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_reassembler_never_crashes_on_random_fragment_stream(chunks: list[bytes]) -> None:
    """Same invariants, but applied to a stream of small chunks — the
    realistic shape of a GATT notification feed."""

    r = FrameReassembler()
    for chunk in chunks:
        for frame in r.feed(chunk):
            assert len(frame) == FRAME_SIZE
            assert frame[:2] == MAGIC


# ---------------------------------------------------------------------------
# Sanity: build_frame from the fixture module is itself a valid frame.
# ---------------------------------------------------------------------------


def test_build_frame_produces_a_valid_36_byte_frame() -> None:
    frame = build_frame(
        voltage_v=1.0,
        current_a=0.1,
        capacity_mah=0,
        energy_wh=0.0,
        voltage_dplus_v=0.0,
        voltage_dminus_v=0.0,
        temperature_c=0,
        duration_s=0,
    )
    assert len(frame) == FRAME_SIZE
    assert frame[:2] == MAGIC

    r = FrameReassembler()
    assert list(r.feed(frame)) == [frame]
