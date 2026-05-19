"""Public-API integration tests for :class:`atorch_ble.AtorchBleParser`.

End-to-end byte-stream-in → readings-list-out scenarios: single frames,
multiple frames in one call, frames fragmented across calls, garbage
interleaved with valid frames, ``UnsupportedPacketType`` propagation,
and ``error_count`` accumulation across :class:`InvalidPacket` failures.
"""

from __future__ import annotations

import pytest

from atorch_ble import (
    AtorchBleParser,
    InvalidPacket,
    UnsupportedPacketType,
    UsbMeterReading,
    __version__,
)

from .fixtures.known_frames import (
    CANONICAL_FRAME,
    MID_FRAME,
    ZERO_FRAME,
    build_frame,
    frame_with_corrupted_checksum,
    frame_with_packet_type,
)

# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_public_api_imports_and_version() -> None:
    assert isinstance(__version__, str)
    assert __version__  # non-empty
    assert AtorchBleParser is not None
    assert UsbMeterReading is not None
    assert issubclass(InvalidPacket, Exception)
    assert issubclass(UnsupportedPacketType, InvalidPacket)


def test_parser_initial_state() -> None:
    parser = AtorchBleParser()
    assert parser.error_count == 0
    assert parser.last_error is None


# ---------------------------------------------------------------------------
# Single-frame end-to-end
# ---------------------------------------------------------------------------


def test_feed_valid_frame_returns_reading() -> None:
    parser = AtorchBleParser()
    readings = parser.feed(CANONICAL_FRAME)

    assert len(readings) == 1
    assert isinstance(readings[0], UsbMeterReading)
    assert readings[0].voltage_v == 5.12
    assert readings[0].current_a == 1.23
    assert parser.error_count == 0
    assert parser.last_error is None


def test_feed_garbage_bytes_returns_empty_and_does_not_raise() -> None:
    parser = AtorchBleParser()
    readings = parser.feed(b"\x00" * 50)
    # Reassembler filters by magic; garbage never reaches the decoder.
    assert readings == []
    assert parser.error_count == 0
    assert parser.last_error is None


def test_feed_handles_split_notifications() -> None:
    """Fragment a frame across two feed() calls (23 + 13 bytes)."""

    parser = AtorchBleParser()
    frame = build_frame(
        voltage_v=12.0,
        current_a=0.5,
        capacity_mah=10,
        energy_wh=0.1,
        voltage_dplus_v=0.0,
        voltage_dminus_v=0.0,
        temperature_c=20,
        duration_s=5,
    )

    first = parser.feed(frame[:23])
    assert first == []
    second = parser.feed(frame[23:])
    assert len(second) == 1
    assert second[0].voltage_v == 12.0


# ---------------------------------------------------------------------------
# Multiple frames per call / per stream
# ---------------------------------------------------------------------------


def test_feed_multiple_frames_in_one_call() -> None:
    parser = AtorchBleParser()
    readings = parser.feed(CANONICAL_FRAME + MID_FRAME + ZERO_FRAME)
    assert len(readings) == 3
    assert readings[0].voltage_v == 5.12
    assert readings[1].voltage_v == 9.00
    assert readings[2].voltage_v == 0.0
    assert parser.error_count == 0


def test_feed_garbage_interleaved_with_valid_frames() -> None:
    parser = AtorchBleParser()
    out = parser.feed(b"\xde\xad" + CANONICAL_FRAME + b"\x00\x00\x00" + MID_FRAME)
    assert len(out) == 2
    assert out[0].voltage_v == 5.12
    assert out[1].voltage_v == 9.00
    assert parser.error_count == 0


def test_feed_fragmented_across_many_calls() -> None:
    parser = AtorchBleParser()
    stream = CANONICAL_FRAME + MID_FRAME
    chunk_size = 7
    collected: list[UsbMeterReading] = []
    for start in range(0, len(stream), chunk_size):
        collected.extend(parser.feed(stream[start : start + chunk_size]))
    assert len(collected) == 2
    assert collected[0].voltage_v == 5.12
    assert collected[1].voltage_v == 9.00


# ---------------------------------------------------------------------------
# UnsupportedPacketType propagation
# ---------------------------------------------------------------------------


def test_feed_unsupported_packet_type_propagates() -> None:
    parser = AtorchBleParser()
    frame = frame_with_packet_type(0x02)
    with pytest.raises(UnsupportedPacketType) as exc_info:
        parser.feed(frame)
    assert exc_info.value.packet_type == 0x02
    # UnsupportedPacketType is NOT counted as a swallowed error.
    assert parser.error_count == 0
    assert parser.last_error is None


def test_feed_unsupported_packet_type_propagates_across_multi_frame_call() -> None:
    """When a batch contains a valid frame followed by a 0x02 frame, the
    valid frame is decoded into the in-flight list, then the exception
    propagates — the caller does not receive the partial list, but the
    parser's state is consistent for the next call."""

    parser = AtorchBleParser()
    bad = frame_with_packet_type(0x01)
    with pytest.raises(UnsupportedPacketType) as exc_info:
        parser.feed(CANONICAL_FRAME + bad)
    assert exc_info.value.packet_type == 0x01


# ---------------------------------------------------------------------------
# InvalidPacket swallowing + error_count accumulation
# ---------------------------------------------------------------------------


def test_feed_swallows_invalid_packet_and_increments_error_count() -> None:
    """Manually corrupt a checksum byte to trigger ``InvalidPacket``
    inside the decoder. The parser facade must swallow it, record the
    error, and not raise."""

    parser = AtorchBleParser()
    readings = parser.feed(frame_with_corrupted_checksum())
    assert readings == []
    assert parser.error_count == 1
    assert parser.last_error is not None


def test_error_count_accumulates_across_calls() -> None:
    parser = AtorchBleParser()
    parser.feed(frame_with_corrupted_checksum())
    parser.feed(frame_with_corrupted_checksum(MID_FRAME))
    assert parser.error_count == 2


def test_mixed_stream_one_valid_one_invalid_yields_one_and_records_one_error() -> None:
    """A two-frame stream where the second frame has a corrupted
    checksum: the valid frame must decode, the invalid one must be
    swallowed and counted."""

    parser = AtorchBleParser()
    readings = parser.feed(CANONICAL_FRAME + frame_with_corrupted_checksum(MID_FRAME))
    assert len(readings) == 1
    assert readings[0].voltage_v == 5.12
    assert parser.error_count == 1


# ---------------------------------------------------------------------------
# Coverage backstop for tests/__init__.py and fixtures package imports.
# ---------------------------------------------------------------------------


def test_fixtures_package_is_importable() -> None:
    """Importing the fixtures package executes its ``__init__.py``,
    keeping it counted toward coverage even though it has no code."""

    from . import fixtures
    from .fixtures import known_frames

    assert fixtures is not None
    assert hasattr(known_frames, "build_frame")
