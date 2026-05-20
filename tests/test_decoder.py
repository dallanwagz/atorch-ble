"""Comprehensive tests for :mod:`atorch_ble._decoder`.

Covers every behavior listed in ticket #3's acceptance criteria: field
scaling, big-endian decoding, duration-component arithmetic, rejection
gates (length, magic, direction, unsupported packet type), and (when
enabled by the shared flag) checksum validation.
"""

from __future__ import annotations

import pytest

from atorch_ble import InvalidPacket, UnsupportedPacketType, UsbMeterReading
from atorch_ble._decoder import decode_usb_meter

from .fixtures.known_frames import (
    CANONICAL_EXPECTED,
    CANONICAL_FRAME,
    MAX_EXPECTED,
    MAX_FRAME,
    MID_EXPECTED,
    MID_FRAME,
    REAL_CAPTURED_EXPECTED,
    REAL_CAPTURED_FRAME,
    ZERO_EXPECTED,
    ZERO_FRAME,
    _compute_checksum,
    build_frame,
    frame_too_long,
    frame_too_short,
    frame_with_bad_direction,
    frame_with_bad_magic,
    frame_with_corrupted_checksum,
    frame_with_packet_type,
)


def _reading_dict(reading: UsbMeterReading) -> dict[str, float | int]:
    return {
        "voltage_v": reading.voltage_v,
        "current_a": reading.current_a,
        "capacity_mah": reading.capacity_mah,
        "energy_wh": reading.energy_wh,
        "voltage_dplus_v": reading.voltage_dplus_v,
        "voltage_dminus_v": reading.voltage_dminus_v,
        "temperature_c": reading.temperature_c,
        "duration_s": reading.duration_s,
    }


# ---------------------------------------------------------------------------
# Happy-path: canonical, zero, max, mid-range frames
# ---------------------------------------------------------------------------


def test_decode_canonical_frame_matches_hand_computed_expected() -> None:
    reading = decode_usb_meter(CANONICAL_FRAME)
    assert _reading_dict(reading) == CANONICAL_EXPECTED


def test_decode_zero_frame() -> None:
    reading = decode_usb_meter(ZERO_FRAME)
    assert _reading_dict(reading) == ZERO_EXPECTED


def test_decode_max_frame() -> None:
    reading = decode_usb_meter(MAX_FRAME)
    assert _reading_dict(reading) == MAX_EXPECTED


def test_decode_mid_range_frame() -> None:
    reading = decode_usb_meter(MID_FRAME)
    assert _reading_dict(reading) == MID_EXPECTED


# ---------------------------------------------------------------------------
# Field-by-field invariants on the canonical frame
# ---------------------------------------------------------------------------


def test_voltage_scaled_by_100() -> None:
    reading = decode_usb_meter(CANONICAL_FRAME)
    assert reading.voltage_v == 5.12


def test_current_scaled_by_100() -> None:
    reading = decode_usb_meter(CANONICAL_FRAME)
    assert reading.current_a == 1.23


def test_capacity_is_raw_mah() -> None:
    reading = decode_usb_meter(CANONICAL_FRAME)
    assert reading.capacity_mah == 456


def test_energy_scaled_by_100() -> None:
    reading = decode_usb_meter(CANONICAL_FRAME)
    assert reading.energy_wh == 7.89


def test_voltage_dplus_dminus_scaled_by_100() -> None:
    reading = decode_usb_meter(CANONICAL_FRAME)
    assert reading.voltage_dplus_v == 2.71
    assert reading.voltage_dminus_v == 2.72


def test_duration_arithmetic_combines_components() -> None:
    reading = decode_usb_meter(CANONICAL_FRAME)
    assert reading.duration_s == 1 * 86400 + 2 * 3600 + 3 * 60 + 4


def test_duration_at_255_day_rollover_not_reset() -> None:
    """255 days is the documented ceiling at which the wire format would
    wrap a u8 day counter; the decoder simply adds days*86400, so a
    255-day frame must decode to a value larger than 254 * 86400."""

    frame = build_frame(
        voltage_v=0.0,
        current_a=0.0,
        capacity_mah=0,
        energy_wh=0.0,
        voltage_dplus_v=0.0,
        voltage_dminus_v=0.0,
        temperature_c=0,
        duration_s=255 * 86400 + 1 * 3600 + 2 * 60 + 3,
    )
    reading = decode_usb_meter(frame)
    assert reading.duration_s == 255 * 86400 + 1 * 3600 + 2 * 60 + 3


def test_temperature_is_unsigned_u16() -> None:
    """A 0xFFFF temperature slot must decode to 65535, not -1 or 0."""

    frame = bytearray(CANONICAL_FRAME)
    frame[0x15:0x17] = b"\xff\xff"
    # Recompute the checksum so this still passes the gate.
    frame[0x23] = _compute_checksum(frame)
    reading = decode_usb_meter(bytes(frame))
    assert reading.temperature_c == 65535


def test_big_endian_voltage_encoding() -> None:
    """0x010000 in big-endian (with /100 divisor) is 655.36 V."""

    raw = 0x010000  # = 65_536
    frame = bytearray(CANONICAL_FRAME)
    frame[0x04:0x07] = raw.to_bytes(3, "big")
    frame[0x23] = _compute_checksum(frame)
    reading = decode_usb_meter(bytes(frame))
    assert reading.voltage_v == raw / 100.0


# ---------------------------------------------------------------------------
# Rejection gates
# ---------------------------------------------------------------------------


def test_rejects_wrong_length_too_short() -> None:
    with pytest.raises(InvalidPacket):
        decode_usb_meter(frame_too_short())


def test_rejects_wrong_length_too_long() -> None:
    with pytest.raises(InvalidPacket):
        decode_usb_meter(frame_too_long())


def test_rejects_bad_magic() -> None:
    with pytest.raises(InvalidPacket):
        decode_usb_meter(frame_with_bad_magic())


def test_rejects_wrong_direction() -> None:
    with pytest.raises(InvalidPacket):
        decode_usb_meter(frame_with_bad_direction())


@pytest.mark.parametrize("packet_type", [0x01, 0x02])
def test_rejects_unsupported_packet_type(packet_type: int) -> None:
    frame = frame_with_packet_type(packet_type)
    with pytest.raises(UnsupportedPacketType) as excinfo:
        decode_usb_meter(frame)
    assert excinfo.value.packet_type == packet_type


def test_unsupported_packet_type_is_invalid_packet_subclass() -> None:
    """Documented hierarchy: UnsupportedPacketType extends InvalidPacket."""

    assert issubclass(UnsupportedPacketType, InvalidPacket)


# ---------------------------------------------------------------------------
# Checksum validation
# ---------------------------------------------------------------------------


def test_corrupted_checksum_raises_invalid_packet() -> None:
    with pytest.raises(InvalidPacket):
        decode_usb_meter(frame_with_corrupted_checksum())


def test_canonical_frame_passes_checksum_gate() -> None:
    """The build_frame helper computes the same XOR formula the decoder
    enforces, so the canonical frame must decode without raising."""

    reading = decode_usb_meter(CANONICAL_FRAME)
    assert isinstance(reading, UsbMeterReading)


def test_build_frame_checksum_byte_matches_documented_formula() -> None:
    """Independent of the gate: the fixture's checksum byte must equal
    the formula output. This guards against the fixture builder
    silently drifting from the decoder's expectation."""

    expected = (sum(CANONICAL_FRAME[0x03:0x23]) & 0xFF) ^ 0x44
    assert CANONICAL_FRAME[0x23] == expected


# ---------------------------------------------------------------------------
# Real captured frame (golden regression vector)
# ---------------------------------------------------------------------------


def test_decode_real_captured_frame_matches_hand_computed_expected() -> None:
    """A real J7-C frame captured from a live meter must decode to its
    hand-computed field values. This is the regression anchor for the
    checksum fix — under the previous (wrong) sum range and offset this
    real frame failed the checksum gate."""

    reading = decode_usb_meter(REAL_CAPTURED_FRAME)
    assert _reading_dict(reading) == REAL_CAPTURED_EXPECTED


def test_real_captured_frame_checksum_byte_is_authoritative() -> None:
    """The captured frame's own trailing byte must satisfy the checksum
    formula — proving the formula was reverse-engineered from real
    hardware output, not asserted self-consistently against a fixture."""

    expected = (sum(REAL_CAPTURED_FRAME[0x03:0x23]) & 0xFF) ^ 0x44
    assert REAL_CAPTURED_FRAME[0x23] == expected
    assert REAL_CAPTURED_FRAME[0x23] == 0xD8
