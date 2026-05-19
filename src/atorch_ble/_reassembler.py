"""Stateful reassembler for Atorch BLE notification frames.

The J7-C and related Atorch USB/AC/DC meters publish each 36-byte measurement
payload across one or more GATT notifications. This module owns the byte-level
state machine that turns an arbitrary stream of notification fragments back
into whole 36-byte frames.

The reassembler is intentionally pure-byte and synchronous:

* No ``bleak`` / Bluetooth I/O.
* No ``logging``.
* No Home Assistant imports.
* No ``asyncio``.

Checksum validation and field decoding are out of scope; see the packet
decoder module for those concerns. This module commits only to:

* Yielded frames start with ``FF 55``.
* Yielded frames are exactly :data:`FRAME_SIZE` bytes.
* The byte immediately following the magic (the direction byte) equals
  ``0x01`` at the moment the frame is committed.
"""

from __future__ import annotations

from collections.abc import Iterator

FRAME_SIZE: int = 36
"""Total size of an Atorch measurement payload, in bytes."""

MAGIC: bytes = b"\xff\x55"
"""Two-byte frame start marker."""

MAX_BUFFER: int = 4 * FRAME_SIZE
"""Upper bound on retained buffer bytes. Oldest bytes are dropped past this."""

_DIRECTION_OK: int = 0x01
"""Only direction byte we accept directly after the magic header."""


class FrameReassembler:
    """Buffers raw BLE notification bytes and yields complete 36-byte frames.

    The reassembler is stateful: callers feed it whatever ``bytes`` arrive on
    the notification characteristic, and each call to :meth:`feed` returns an
    iterator of zero or more complete frames committed by that call.

    Instances are not thread-safe; ``bleak`` invokes notification callbacks
    serially from a single asyncio task, which matches this design.
    """

    __slots__ = ("_buf",)

    def __init__(self) -> None:
        self._buf: bytearray = bytearray()

    def feed(self, data: bytes) -> Iterator[bytes]:
        """Append ``data`` to the buffer and yield any complete frames.

        Yields each committed frame as an immutable :class:`bytes` object of
        exactly :data:`FRAME_SIZE` bytes. Garbage prefixes, implausible
        candidate headers, and oversize buffers are silently dropped.
        """

        self._buf.extend(data)

        # Cap retained buffer up front so a flood of junk can never grow
        # the buffer past MAX_BUFFER.
        if len(self._buf) > MAX_BUFFER:
            del self._buf[: len(self._buf) - MAX_BUFFER]

        while True:
            idx = self._buf.find(MAGIC)
            if idx < 0:
                # No magic anywhere. Keep only the trailing byte in case it
                # is the first half of a header straddling the next chunk.
                if len(self._buf) > 1:
                    del self._buf[: len(self._buf) - 1]
                return

            if idx > 0:
                del self._buf[:idx]

            # Need at least the magic + direction byte to check plausibility,
            # and FRAME_SIZE bytes to actually emit a frame.
            if len(self._buf) < 3:
                return

            if self._buf[2] != _DIRECTION_OK:
                # Bad candidate header. Drop the first byte and keep scanning
                # from the next position; the buffer may still contain a
                # real header further on.
                del self._buf[:1]
                continue

            if len(self._buf) < FRAME_SIZE:
                # Plausible header, but not enough bytes yet.
                return

            frame = bytes(self._buf[:FRAME_SIZE])
            del self._buf[:FRAME_SIZE]
            yield frame
            # Loop to look for additional frames already in the buffer.
