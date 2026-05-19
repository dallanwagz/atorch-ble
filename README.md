# atorch-ble

A standalone Python parser for the Atorch BLE protocol used by USB/AC/DC power
meters such as the J7-C and UC96. The package provides byte-level
notification-frame reassembly, packet decoding, and typed dataclasses for
measurements, with no Home Assistant dependency so it can be used from any
async or sync Python program. This package is consumed by the
[`atorch_ble` Home Assistant integration](https://github.com/dallanwagz/j7c_ha),
which declares it as a `manifest.json` requirement following the
Bluetooth-Devices org pattern that keeps raw byte parsing out of HA Core.

**Status:** v0.1 — initial release, J7-C / packet type `0x03` only.

## Installation

```bash
pip install atorch-ble
```

Requires Python 3.12 or newer.

## Usage

```python
from atorch_ble import AtorchBleParser, UnsupportedPacketType, UsbMeterReading

# A canonical 36-byte J7-C USB-meter frame (synthetic, derived from the
# documented byte layout). In real use you'd feed the bytes you receive
# from a bleak notification callback.
frame = bytes.fromhex(
    "ff55010300020000007b0001c800000315010f0110001b01020304"
    "000000000000ec0000"
)

parser = AtorchBleParser()
try:
    readings: list[UsbMeterReading] = parser.feed(frame)
except UnsupportedPacketType as exc:
    # Raised for non-J7-C packet types (e.g. DL24/UD18 DC meters).
    print(f"unsupported packet type: 0x{exc.packet_type:02x}")
    readings = []

for r in readings:
    print(f"voltage:     {r.voltage_v} V")
    print(f"current:     {r.current_a} A")
    print(f"capacity:    {r.capacity_mah} mAh")
    print(f"energy:      {r.energy_wh} Wh")
    print(f"D+ / D-:     {r.voltage_dplus_v} V / {r.voltage_dminus_v} V")
    print(f"temperature: {r.temperature_c} C")
    print(f"duration:    {r.duration_s} s")
```

`AtorchBleParser.feed()` accepts raw bytes from a single BLE notification
callback (zero, partial, one, or multiple frames) and returns the list of
fully decoded `UsbMeterReading` instances. Recoverable decode failures
(bad length, magic, direction byte, or checksum mismatch) are swallowed
and recorded on `parser.error_count` / `parser.last_error`;
`UnsupportedPacketType` is re-raised so callers can surface it to the user.

## Supported devices

| Device      | Packet type | Status                                          |
| ----------- | ----------- | ----------------------------------------------- |
| J7-C        | `0x03`      | Confirmed against documented byte layout        |
| UC96        | `0x03`      | Same protocol family, untested                  |
| DL24 / UD18 | `0x01–0x02` | Detected; raises `UnsupportedPacketType`        |

## Development

```bash
git clone https://github.com/dallanwagz/atorch-ble
cd atorch-ble
pip install -e ".[dev]"
pytest
```

Quality gates: [`ruff`](https://github.com/astral-sh/ruff) for lint and
formatting, [`mypy --strict`](https://mypy.readthedocs.io/) for typing, and
[`pytest`](https://docs.pytest.org/) with a 95% coverage floor.

## License

MIT — see [`LICENSE`](LICENSE).
