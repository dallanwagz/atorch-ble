# Changelog

## [0.1.1] - 2026-05-19

### Fixed
- USB-meter checksum validation. The decoder summed the wrong byte range
  (`payload[2:33]`) and compared it against the wrong offset (`payload[0x21]`,
  a constant data byte), so real J7-C frames failed the checksum gate roughly
  99.7% of the time — decoding only on a chance collision. The checksum is
  `(sum(payload[0x03:0x23]) & 0xFF) ^ 0x44` stored in the final byte
  (`payload[0x23]`), reverse-engineered and confirmed against 639 frames
  captured from a live meter.

### Added
- `REAL_CAPTURED_FRAME` golden test vector: a real J7-C frame captured from
  hardware, decoded against hand-computed expected values, anchoring the
  decoder against regressions.

## [0.1.0] - 2026-05-19

Initial release.

### Added
- BLE notification frame reassembler handling fragmented Atorch payloads
- 36-byte USB-meter packet decoder for J7-C (packet type 0x03), big-endian fields, mandatory checksum validation
- Public API: `AtorchBleParser`, `UsbMeterReading`, `InvalidPacket`, `UnsupportedPacketType`
- Comprehensive unit tests with Hypothesis property test on the reassembler
- 95% coverage gate enforced in CI
- Type-checked with `mypy --strict`; ships `py.typed`
