"""Smoke tests for :mod:`atorch_ble._decoder`.

Comprehensive coverage (real-capture fixtures, hypothesis fuzzing, the
checksum-validation flip) is ticket #4; this module only verifies that the
happy path and the four documented rejection gates behave as specified.
"""

from __future__ import annotations

import pytest

from atorch_ble._decoder import (
    InvalidPacket,
    UnsupportedPacketType,
    UsbMeterReading,
    decode_usb_meter,
)


def _u24_be(value: int) -> bytes:
    return value.to_bytes(3, "big", signed=False)


def _u32_be(value: int) -> bytes:
    return value.to_bytes(4, "big", signed=False)


def _u16_be(value: int) -> bytes:
    return value.to_bytes(2, "big", signed=False)


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
    """Build a 36-byte Atorch USB-meter frame from named fields.

    Inverts the decoder's field math (e.g. multiplies voltage by 100) and
    splits ``duration_s`` back into the days/hours/minutes/seconds tuple
    the wire format uses. Reserved bytes and the tail are zero-filled. The
    checksum is computed per the documented formula so the frame stays
    valid if/when :data:`atorch_ble._decoder._CHECKSUM_VALIDATED` flips
    to ``True``.

    Ticket #4 will port this helper to a shared fixtures module.
    """

    body = bytearray(36)
    body[0:2] = b"\xff\x55"
    body[2] = 0x01
    body[3] = packet_type
    body[0x04:0x07] = _u24_be(round(voltage_v * 100))
    body[0x07:0x0A] = _u24_be(round(current_a * 100))
    body[0x0A:0x0D] = _u24_be(capacity_mah)
    body[0x0D:0x11] = _u32_be(round(energy_wh * 100))
    body[0x11:0x13] = _u16_be(round(voltage_dplus_v * 100))
    body[0x13:0x15] = _u16_be(round(voltage_dminus_v * 100))
    body[0x15:0x17] = _u16_be(temperature_c)

    days, rem = divmod(duration_s, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    body[0x17] = days
    body[0x18] = hours
    body[0x19] = minutes
    body[0x1A] = seconds

    # 0x1B..0x20 reserved (zero-filled by bytearray(36)).
    body[0x21] = (sum(body[2:33]) & 0xFF) ^ 0x44
    # 0x22..0x23 tail (zero-filled).

    return bytes(body)


def test_decode_usb_meter_happy_path() -> None:
    frame = build_frame(
        voltage_v=5.12,
        current_a=1.23,
        capacity_mah=456,
        energy_wh=7.89,
        voltage_dplus_v=2.71,
        voltage_dminus_v=2.72,
        temperature_c=27,
        duration_s=1 * 86400 + 2 * 3600 + 3 * 60 + 4,
    )

    reading = decode_usb_meter(frame)

    assert reading == UsbMeterReading(
        voltage_v=5.12,
        current_a=1.23,
        capacity_mah=456,
        energy_wh=7.89,
        voltage_dplus_v=2.71,
        voltage_dminus_v=2.72,
        temperature_c=27,
        duration_s=1 * 86400 + 2 * 3600 + 3 * 60 + 4,
    )


def test_decode_usb_meter_rejects_bad_magic() -> None:
    frame = bytearray(
        build_frame(
            voltage_v=5.0,
            current_a=1.0,
            capacity_mah=0,
            energy_wh=0.0,
            voltage_dplus_v=0.0,
            voltage_dminus_v=0.0,
            temperature_c=25,
            duration_s=0,
        )
    )
    frame[0] = 0x00  # break the magic

    with pytest.raises(InvalidPacket):
        decode_usb_meter(bytes(frame))


def test_decode_usb_meter_rejects_wrong_length() -> None:
    with pytest.raises(InvalidPacket):
        decode_usb_meter(b"\xff\x55\x01\x03" + b"\x00" * 10)


def test_decode_usb_meter_rejects_wrong_direction() -> None:
    frame = bytearray(
        build_frame(
            voltage_v=5.0,
            current_a=1.0,
            capacity_mah=0,
            energy_wh=0.0,
            voltage_dplus_v=0.0,
            voltage_dminus_v=0.0,
            temperature_c=25,
            duration_s=0,
        )
    )
    frame[2] = 0x02  # not from-device

    with pytest.raises(InvalidPacket):
        decode_usb_meter(bytes(frame))


def test_decode_usb_meter_rejects_unsupported_packet_type() -> None:
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

    with pytest.raises(UnsupportedPacketType) as excinfo:
        decode_usb_meter(frame)
    assert excinfo.value.packet_type == 0x02
