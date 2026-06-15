"""Pure-function decoder for Atorch USB-meter (J7-C) measurement frames.

This module turns a fully reassembled 36-byte Atorch payload into a typed,
SI-unit :class:`UsbMeterReading` dataclass. The decoder is intentionally
pure:

* No I/O, no logging, no global state.
* Input is untrusted bytes; the decoder validates length first and never
  indexes past the buffer.
* Power (W) and resistance (Ω) are explicitly **not** computed here — those
  are coordinator-side derivations on the Home Assistant integration.

Only packet type ``0x03`` (J7-C / USB meter) is decoded. Other documented
types (``0x01`` AC meter, ``0x02`` DC meter) are surfaced via
:class:`UnsupportedPacketType` so the HA coordinator can render a repair
issue rather than silently dropping data.
"""

from __future__ import annotations

import dataclasses

_MAGIC: bytes = b"\xff\x55"
_DIR_FROM_DEVICE: int = 0x01
_TYPE_USB_METER: int = 0x03
_EXPECTED_LEN: int = 36


class InvalidPacket(ValueError):
    """Raised when a payload fails structural or checksum validation."""


class UnsupportedPacketType(InvalidPacket):
    """Raised when packet_type byte is not ``0x03`` (J7-C / USB meter)."""

    def __init__(self, packet_type: int) -> None:
        super().__init__(f"unsupported packet type: 0x{packet_type:02x}")
        self.packet_type: int = packet_type


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class UsbMeterReading:
    """Decoded USB-meter measurement in SI / declared units.

    Fields are populated directly from the 36-byte Atorch payload. Power (W)
    is intentionally absent — the HA coordinator computes
    ``power_w = voltage_v * current_a`` and stores it on ``AtorchBleData``.
    """

    voltage_v: float
    current_a: float
    capacity_mah: int
    energy_wh: float
    voltage_dplus_v: float
    voltage_dminus_v: float
    temperature_c: int
    duration_s: int


def decode_usb_meter(payload: bytes) -> UsbMeterReading:
    """Decode a reassembled 36-byte Atorch USB-meter frame (packet type 0x03).

    Power (W) and resistance (Ω) are **not** computed here — those are
    coordinator-side derivations (``voltage_v * current_a``, and
    ``voltage_v / current_a`` when ``current_a > 0``).

    Checksum behaviour: the formula ``(sum(payload[0x03:0x23]) & 0xFF)
    ^ 0x44`` is enforced against the final byte (``payload[0x23]``); on
    mismatch :class:`InvalidPacket` is raised. The formula is confirmed
    against 639 real J7-C frames captured from a live meter — the
    checksum spans the packet-type byte through the last data byte.

    Args:
        payload: The reassembled 36-byte BLE frame.

    Returns:
        A :class:`UsbMeterReading` with all fields populated in SI /
        declared units.

    Raises:
        InvalidPacket: On wrong length, bad magic, wrong direction byte,
            or checksum mismatch.
        UnsupportedPacketType: When the packet-type byte is not ``0x03``.
    """

    if len(payload) != _EXPECTED_LEN:
        raise InvalidPacket(f"expected {_EXPECTED_LEN}-byte payload, got {len(payload)}")

    if payload[0:2] != _MAGIC:
        raise InvalidPacket(f"bad magic: {payload[0:2]!r}")

    if payload[2] != _DIR_FROM_DEVICE:
        raise InvalidPacket(f"bad direction byte: 0x{payload[2]:02x}")

    if payload[3] != _TYPE_USB_METER:
        raise UnsupportedPacketType(packet_type=payload[3])

    expected_checksum = (sum(payload[0x03:0x23]) & 0xFF) ^ 0x44
    if payload[0x23] != expected_checksum:
        raise InvalidPacket(
            f"checksum mismatch: got 0x{payload[0x23]:02x}, expected 0x{expected_checksum:02x}"
        )

    voltage_v = int.from_bytes(payload[0x04:0x07], "big", signed=False) / 100.0
    current_a = int.from_bytes(payload[0x07:0x0A], "big", signed=False) / 100.0
    capacity_mah = int.from_bytes(payload[0x0A:0x0D], "big", signed=False)
    energy_wh = int.from_bytes(payload[0x0D:0x11], "big", signed=False) / 100.0
    voltage_dplus_v = int.from_bytes(payload[0x11:0x13], "big", signed=False) / 100.0
    voltage_dminus_v = int.from_bytes(payload[0x13:0x15], "big", signed=False) / 100.0
    temperature_c = int.from_bytes(payload[0x15:0x17], "big", signed=False)

    # Time record is hours:minutes:seconds, where "hours" is a 16-bit
    # big-endian counter spanning bytes 0x17-0x18 (NOT a days byte + an
    # hours byte). Confirmed against the official Atorch "E_Test" app,
    # which reads ``u16(0x17, 0x18)`` as the hour field and displays
    # HH:MM:SS with no days component. The earlier days/hours split was
    # numerically identical only while total runtime stayed under 256
    # hours (high byte zero); past ~10.6 days continuous it under-reported.
    hours = int.from_bytes(payload[0x17:0x19], "big", signed=False)
    minutes = payload[0x19]
    seconds = payload[0x1A]
    duration_s = hours * 3600 + minutes * 60 + seconds

    return UsbMeterReading(
        voltage_v=voltage_v,
        current_a=current_a,
        capacity_mah=capacity_mah,
        energy_wh=energy_wh,
        voltage_dplus_v=voltage_dplus_v,
        voltage_dminus_v=voltage_dminus_v,
        temperature_c=temperature_c,
        duration_s=duration_s,
    )
