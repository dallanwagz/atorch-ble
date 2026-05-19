# Changelog

## [0.1.0] - 2026-05-19

Initial release.

### Added
- BLE notification frame reassembler handling fragmented Atorch payloads
- 36-byte USB-meter packet decoder for J7-C (packet type 0x03), big-endian fields, mandatory checksum validation
- Public API: `AtorchBleParser`, `UsbMeterReading`, `InvalidPacket`, `UnsupportedPacketType`
- Comprehensive unit tests with Hypothesis property test on the reassembler
- 95% coverage gate enforced in CI
- Type-checked with `mypy --strict`; ships `py.typed`
