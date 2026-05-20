"""Known-good and adversarial Atorch BLE frame fixtures.

Provenance
==========

Ticket #4 acceptance criteria allow EITHER Option A (real captured frame
from an external reference, cited by URL) or Option B (canonical synthetic
frame, every byte annotated from the offset table in PROJECT_CONTEXT.md).

**This module uses Option B (canonical synthetic).**

Rationale: no live J7-C captures are checked in to this repository at the
time of v0.1.0 prep, and the project's authoritative byte-layout table
lives in ``PROJECT_CONTEXT.md`` (in the consumer repo
``dallanwagz/j7c_ha``, under ``docs/spine/PROJECT_CONTEXT.md``). The
synthetic frame below is constructed from that table; the expected
decoded values are computed by hand from the same table — **not** by
calling the decoder under test. The checksum byte is computed via the
documented XOR formula so that the frame stays valid when the decoder's
checksum gate.

Byte layout (USB-meter packet type 0x03), per PROJECT_CONTEXT.md:

    Offset  Len  Field             Encoding             Divisor / Notes
    0x00    2    magic             literal              b"\\xff\\x55"
    0x02    1    direction         u8                   0x01 = from device
    0x03    1    packet_type       u8                   0x03 = USB meter
    0x04    3    voltage           u24 big-endian       /100  -> volts
    0x07    3    current           u24 big-endian       /100  -> amps
    0x0A    3    capacity_mah      u24 big-endian       raw mAh
    0x0D    4    energy            u32 big-endian       /100  -> watt-hours
    0x11    2    voltage_d_plus    u16 big-endian       /100  -> volts
    0x13    2    voltage_d_minus   u16 big-endian       /100  -> volts
    0x15    2    temperature       u16 big-endian       raw degrees C (unsigned)
    0x17    1    duration_days     u8
    0x18    1    duration_hours    u8
    0x19    1    duration_minutes  u8
    0x1A    1    duration_seconds  u8
    0x1B    8    reserved          vendor framing (not decoded)
    0x23    1    checksum          (sum(payload[0x03:0x23]) & 0xFF) ^ 0x44
    ---------------------------------------------------------------
    Total length:                  36 bytes

The checksum formula and offset are confirmed against 639 real J7-C
frames captured from a live meter (see ``REAL_CAPTURED_FRAME`` below).
"""

from __future__ import annotations

from typing import Final

FRAME_SIZE: Final[int] = 36


def _compute_checksum(body: bytes | bytearray) -> int:
    """Compute the Atorch checksum byte for an in-progress frame.

    The formula is ``(sum(body[0x03:0x23]) & 0xFF) ^ 0x44`` — the sum
    spans the packet-type byte through the last data byte, stored at
    ``body[0x23]``. Confirmed against 639 real captured frames.
    Centralized here so the (range, XOR-mask) triple has one home.
    """

    return (sum(body[0x03:0x23]) & 0xFF) ^ 0x44


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
    direction: int = 0x01,
) -> bytes:
    """Build a 36-byte Atorch USB-meter frame from named fields.

    The helper inverts the decoder's field math (e.g. multiplies voltage
    by 100) and splits ``duration_s`` back into the days/hours/minutes/
    seconds tuple the wire format uses. Reserved bytes and the trailing
    framing bytes are zero-filled. The checksum is computed per the
    documented XOR formula so the frame is accepted by the decoder
    whether or not its checksum gate is enabled.
    """

    body = bytearray(FRAME_SIZE)
    body[0:2] = b"\xff\x55"
    body[2] = direction
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

    # 0x1B..0x22 reserved / vendor framing (zero-filled).
    body[0x23] = _compute_checksum(body)
    return bytes(body)


# ---------------------------------------------------------------------------
# Canonical synthetic reference frame
# ---------------------------------------------------------------------------
#
# Mid-range plausible operating point for a USB meter in active use.
# Source: synthetic, derived from PROJECT_CONTEXT.md offset table (see
# this module's docstring). Expected values below are hand-computed from
# the same table; do NOT regenerate them by calling the decoder.

CANONICAL_FIELDS: Final[dict[str, float | int]] = {
    "voltage_v": 5.12,
    "current_a": 1.23,
    "capacity_mah": 456,
    "energy_wh": 7.89,
    "voltage_dplus_v": 2.71,
    "voltage_dminus_v": 2.72,
    "temperature_c": 27,
    # 1 day, 2 hours, 3 minutes, 4 seconds = 93_784 s
    "duration_s": 1 * 86400 + 2 * 3600 + 3 * 60 + 4,
}

CANONICAL_FRAME: Final[bytes] = build_frame(**CANONICAL_FIELDS)  # type: ignore[arg-type]

CANONICAL_EXPECTED: Final[dict[str, float | int]] = dict(CANONICAL_FIELDS)


# ---------------------------------------------------------------------------
# Edge-case synthetic frames (with hand-computed expected dicts)
# ---------------------------------------------------------------------------

ZERO_FIELDS: Final[dict[str, float | int]] = {
    "voltage_v": 0.0,
    "current_a": 0.0,
    "capacity_mah": 0,
    "energy_wh": 0.0,
    "voltage_dplus_v": 0.0,
    "voltage_dminus_v": 0.0,
    "temperature_c": 0,
    "duration_s": 0,
}
ZERO_FRAME: Final[bytes] = build_frame(**ZERO_FIELDS)  # type: ignore[arg-type]
ZERO_EXPECTED: Final[dict[str, float | int]] = dict(ZERO_FIELDS)


# Max per-field values constrained to each field's wire width:
#   u24 max = 16_777_215     u32 max = 4_294_967_295     u16 max = 65_535
#   day/hr/min/sec are each u8 (255 max).
#
# Voltage/current/energy/d+/d- carry a /100 divisor, so the float value
# of "max raw bytes" is rawmax / 100. Duration: we set each of the four
# duration bytes to 0xFF on the wire — the *decoded* duration is then
# days*86400 + hours*3600 + minutes*60 + seconds with all four
# components at 255. This intentionally exercises the documented
# "duration components are *not* clamped at the day rollover".
MAX_RAW_U24: Final[int] = 0xFFFFFF
MAX_RAW_U32: Final[int] = 0xFFFFFFFF
MAX_RAW_U16: Final[int] = 0xFFFF
MAX_DURATION_S: Final[int] = 255 * 86400 + 255 * 3600 + 255 * 60 + 255


def _build_max_frame() -> bytes:
    """Build the max-per-field frame.

    ``build_frame`` re-splits ``duration_s`` via divmod, which would
    overflow the u8 ``days`` byte if we asked for 22_975_635 seconds.
    Instead we ask for a zero-duration frame, then overwrite the four
    duration bytes with ``0xFF`` directly and recompute the checksum.
    """

    body = bytearray(
        build_frame(
            voltage_v=MAX_RAW_U24 / 100.0,
            current_a=MAX_RAW_U24 / 100.0,
            capacity_mah=MAX_RAW_U24,
            energy_wh=MAX_RAW_U32 / 100.0,
            voltage_dplus_v=MAX_RAW_U16 / 100.0,
            voltage_dminus_v=MAX_RAW_U16 / 100.0,
            temperature_c=MAX_RAW_U16,
            duration_s=0,
        )
    )
    body[0x17] = 0xFF
    body[0x18] = 0xFF
    body[0x19] = 0xFF
    body[0x1A] = 0xFF
    body[0x23] = _compute_checksum(body)
    return bytes(body)


MAX_FRAME: Final[bytes] = _build_max_frame()
MAX_EXPECTED: Final[dict[str, float | int]] = {
    "voltage_v": MAX_RAW_U24 / 100.0,
    "current_a": MAX_RAW_U24 / 100.0,
    "capacity_mah": MAX_RAW_U24,
    "energy_wh": MAX_RAW_U32 / 100.0,
    "voltage_dplus_v": MAX_RAW_U16 / 100.0,
    "voltage_dminus_v": MAX_RAW_U16 / 100.0,
    "temperature_c": MAX_RAW_U16,
    "duration_s": MAX_DURATION_S,
}


MID_FIELDS: Final[dict[str, float | int]] = {
    "voltage_v": 9.00,
    "current_a": 2.50,
    "capacity_mah": 1234,
    "energy_wh": 12.34,
    "voltage_dplus_v": 0.60,
    "voltage_dminus_v": 0.60,
    "temperature_c": 42,
    "duration_s": 3661,  # 1h 1m 1s
}
MID_FRAME: Final[bytes] = build_frame(**MID_FIELDS)  # type: ignore[arg-type]
MID_EXPECTED: Final[dict[str, float | int]] = dict(MID_FIELDS)


# ---------------------------------------------------------------------------
# Real captured frame (golden vector)
# ---------------------------------------------------------------------------
#
# Provenance: Option A — a real J7-C frame captured from a live meter on
# 2026-05-19 via a Bluetooth HCI snoop log of the vendor E_Test app. The
# Atorch wire format is transport-agnostic (identical bytes over BLE GATT
# and Classic SPP). Expected values below are hand-computed from the
# offset table in this module's docstring — NOT by calling the decoder.
#
# This is the regression anchor for the checksum fix: the previous
# decoder used the wrong sum range and checksum offset, so real frames
# like this one failed validation ~99.7% of the time.

REAL_CAPTURED_FRAME: Final[bytes] = bytes.fromhex(
    "ff5501030003860000d2000d6d0000095201190118"
    "0028000409163c0c800000032000d8"
)
REAL_CAPTURED_EXPECTED: Final[dict[str, float | int]] = {
    "voltage_v": 9.02,
    "current_a": 2.10,
    "capacity_mah": 3437,
    "energy_wh": 23.86,
    "voltage_dplus_v": 2.81,
    "voltage_dminus_v": 2.80,
    "temperature_c": 40,
    "duration_s": 4 * 3600 + 9 * 60 + 22,  # 4h 09m 22s = 14_962 s
}


# ---------------------------------------------------------------------------
# Negative fixtures (for decoder rejection / facade swallow tests)
# ---------------------------------------------------------------------------


def frame_with_bad_magic() -> bytes:
    """Canonical frame with the first magic byte zeroed."""

    bad = bytearray(CANONICAL_FRAME)
    bad[0] = 0x00
    return bytes(bad)


def frame_with_bad_direction() -> bytes:
    """Canonical fields packed with a non-from-device direction byte.

    The reassembler will reject this candidate header, so the resulting
    bytes never reach the decoder via the parser facade — but we still
    use it to assert :func:`atorch_ble._decoder.decode_usb_meter`'s
    direction-byte gate when called directly.
    """

    return build_frame(direction=0x02, **CANONICAL_FIELDS)  # type: ignore[arg-type]


def frame_with_packet_type(packet_type: int) -> bytes:
    """Build a structurally valid frame with an arbitrary packet type."""

    return build_frame(packet_type=packet_type, **CANONICAL_FIELDS)  # type: ignore[arg-type]


def frame_too_short() -> bytes:
    """Bytes shorter than the documented 36-byte length."""

    return b"\xff\x55\x01\x03" + b"\x00" * 10


def frame_too_long() -> bytes:
    """Canonical frame with extra trailing bytes appended."""

    return CANONICAL_FRAME + b"\x00" * 4


def frame_with_corrupted_checksum(source: bytes = CANONICAL_FRAME) -> bytes:
    """Return ``source`` with its checksum byte flipped to an invalid value.

    Defaults to corrupting :data:`CANONICAL_FRAME`; pass any other valid
    36-byte Atorch frame to produce a corrupted variant of that frame.
    """

    bad = bytearray(source)
    bad[0x23] = (bad[0x23] ^ 0xFF) & 0xFF
    return bytes(bad)
