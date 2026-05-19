"""Stateful facade combining frame reassembly and packet decoding.

This module is internal — the public re-export lives in
:mod:`atorch_ble.__init__`. See that module's docstring for the package's
role and the consumer integration link.
"""

from __future__ import annotations

from ._decoder import (
    InvalidPacket,
    UnsupportedPacketType,
    UsbMeterReading,
    decode_usb_meter,
)
from ._reassembler import FrameReassembler


class AtorchBleParser:
    """Stateful facade combining frame reassembly and packet decoding.

    Thread-safety: single-threaded. Intended to be driven from one caller —
    typically the bleak notification callback context. Concurrent calls to
    :meth:`feed` from multiple threads are undefined behavior.

    Attributes:
        last_error: Short description of the most recent swallowed decode
            failure, or ``None`` if none has occurred.
        error_count: Monotonic count of swallowed :class:`InvalidPacket`
            failures since construction. The short name is intentional for
            package-local use; consumers (e.g., the HA integration's
            diagnostics dump) typically re-export this value under a more
            specific name like ``parser_error_count`` to disambiguate at
            the consumer's top-level schema.
    """

    __slots__ = ("_reassembler", "error_count", "last_error")

    def __init__(self) -> None:
        self._reassembler: FrameReassembler = FrameReassembler()
        self.last_error: str | None = None
        self.error_count: int = 0

    def feed(self, data: bytes) -> list[UsbMeterReading]:
        """Feed raw BLE notification bytes through reassembly and decoding.

        Args:
            data: Raw bytes from a single BLE notification callback. May
                contain zero, partial, one, or multiple frames.

        Returns:
            Zero or more :class:`UsbMeterReading` instances decoded from
            frames committed during this call.

        Raises:
            UnsupportedPacketType: When the decoder reports a non-``0x03``
                packet type. Re-raised so the HA integration can convert it
                to a repair issue. :class:`InvalidPacket` is **swallowed**
                and recorded on :attr:`last_error` / :attr:`error_count`.
        """

        readings: list[UsbMeterReading] = []
        for frame in self._reassembler.feed(data):
            try:
                readings.append(decode_usb_meter(frame))
            except UnsupportedPacketType:
                raise
            except InvalidPacket as exc:
                self.last_error = str(exc)
                self.error_count += 1
        return readings
