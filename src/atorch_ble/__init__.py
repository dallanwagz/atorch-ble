"""atorch-ble: Atorch-protocol BLE USB power meter frame reassembly and decoding.

This package provides byte-level frame reassembly, packet decoding, and
typed dataclasses for devices using the Atorch BLE protocol (J7-C / UC96
and related USB/AC/DC meters). It has no Home Assistant dependency and
can be used standalone.

Thread-safety: :class:`AtorchBleParser` is single-threaded. It is intended
to be driven from one caller — typically the bleak notification callback
context. Consumers like the HA integration may re-export
:attr:`AtorchBleParser.error_count` under a more specific name such as
``parser_error_count`` in their top-level diagnostics schemas.

This package is consumed by the Home Assistant integration at
https://github.com/dallanwagz/j7c_ha.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import Final

from ._decoder import InvalidPacket, UnsupportedPacketType, UsbMeterReading
from ._parser import AtorchBleParser


def _resolve_version() -> str:
    try:
        return _pkg_version("atorch-ble")
    except PackageNotFoundError:  # editable install without metadata
        return "0.0.0+local"


__version__: Final[str] = _resolve_version()

__all__: Final[tuple[str, ...]] = (
    "AtorchBleParser",
    "InvalidPacket",
    "UnsupportedPacketType",
    "UsbMeterReading",
    "__version__",
)
