# atorch-ble

A standalone Python parser for the Atorch BLE protocol used by USB/AC/DC power
meters such as the J7-C and UC96. The package provides byte-level
notification-frame reassembly, packet decoding, and typed dataclasses for
measurements, with no Home Assistant dependency so it can be used from any
async or sync Python program. This package is consumed by the `atorch_ble`
Home Assistant integration (see https://github.com/dallanwagz/j7c_ha), which
declares it as a `manifest.json` requirement following the Bluetooth-Devices
org pattern that keeps raw byte parsing out of HA Core.
