"""Tests for the :class:`atorch_ble.AtorchBleParser` facade.

These exercise the public API surface locked by ticket #6: the facade
class, the re-exported dataclass / exception types, ``__version__``, and
the documented error-handling contract (swallow :class:`InvalidPacket`,
re-raise :class:`UnsupportedPacketType`).
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


def build_frame(
    *,
    voltage_v: float,
    current_a: float,
    capacity_mah: int,
    energy_wh: float,
    voltage_dplus_v: float,
    voltage_dminus_v: float,
    temperature_c: int,
    duration_s: int,
    packet_type: int = 0x03,
) -> bytes:
    """Inline copy of the decoder-test frame builder.

    Duplicated rather than imported because pytest discovers ``tests/`` as
    a flat namespace (no ``__init__.py``) and ``mypy --strict`` rejects
    cross-test imports under that layout. Ticket #4 will port this helper
    into a shared fixtures module.
    """

    body = bytearray(36)
    body[0:2] = b"\xff\x55"
    body[2] = 0x01
    body[3] = packet_type
    body[0x04:0x07] = round(voltage_v * 100).to_bytes(3, "big")
    body[0x07:0x0A] = round(current_a * 100).to_bytes(3, "big")
    body[0x0A:0x0D] = capacity_mah.to_bytes(3, "big")
    body[0x0D:0x11] = round(energy_wh * 100).to_bytes(4, "big")
    body[0x11:0x13] = round(voltage_dplus_v * 100).to_bytes(2, "big")
    body[0x13:0x15] = round(voltage_dminus_v * 100).to_bytes(2, "big")
    body[0x15:0x17] = temperature_c.to_bytes(2, "big")

    days, rem = divmod(duration_s, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    body[0x17] = days
    body[0x18] = hours
    body[0x19] = minutes
    body[0x1A] = seconds

    body[0x21] = (sum(body[2:33]) & 0xFF) ^ 0x44
    return bytes(body)


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


def test_feed_valid_frame_returns_reading() -> None:
    parser = AtorchBleParser()
    frame = build_frame(
        voltage_v=5.0,
        current_a=1.0,
        capacity_mah=100,
        energy_wh=1.5,
        voltage_dplus_v=2.5,
        voltage_dminus_v=2.5,
        temperature_c=25,
        duration_s=60,
    )

    readings = parser.feed(frame)

    assert len(readings) == 1
    assert isinstance(readings[0], UsbMeterReading)
    assert readings[0].voltage_v == 5.0
    assert readings[0].current_a == 1.0
    assert parser.error_count == 0
    assert parser.last_error is None


def test_feed_garbage_bytes_returns_empty_and_does_not_raise() -> None:
    parser = AtorchBleParser()

    readings = parser.feed(b"\x00" * 50)

    # Reassembler filters by magic, so pure-garbage bytes never reach the
    # decoder — error_count stays at zero.
    assert readings == []
    assert parser.error_count == 0
    assert parser.last_error is None


def test_feed_unsupported_packet_type_propagates() -> None:
    parser = AtorchBleParser()
    # Build a structurally valid frame but with packet_type=0x02 (DC meter).
    frame = build_frame(
        voltage_v=5.0,
        current_a=1.0,
        capacity_mah=0,
        energy_wh=0.0,
        voltage_dplus_v=0.0,
        voltage_dminus_v=0.0,
        temperature_c=25,
        duration_s=0,
        packet_type=0x02,
    )

    with pytest.raises(UnsupportedPacketType) as exc_info:
        parser.feed(frame)

    assert exc_info.value.packet_type == 0x02
    # UnsupportedPacketType is NOT counted as a swallowed error.
    assert parser.error_count == 0
    assert parser.last_error is None


def test_feed_handles_split_notifications() -> None:
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

    # First chunk: not enough bytes to commit a frame.
    first = parser.feed(frame[:20])
    assert first == []

    # Second chunk: completes the frame.
    second = parser.feed(frame[20:])
    assert len(second) == 1
    assert second[0].voltage_v == 12.0
