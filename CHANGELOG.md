# Changelog

## [0.1.2] - 2026-06-15

### Fixed
- USB-meter duration decode. The decoder read byte `0x17` as a `days`
  counter and byte `0x18` as `hours`, then computed
  `days*86400 + hours*3600 + …`. The wire format is actually
  `hours:minutes:seconds`, where `hours` is a **16-bit big-endian**
  counter spanning bytes `0x17`-`0x18` (there is no days byte). The two
  interpretations are numerically identical only while total runtime
  stays under 256 hours (high byte zero); past ~10.6 days continuous the
  old decode under-reported. Now decoded as
  `u16(0x17:0x19)*3600 + minutes*60 + seconds`. Confirmed against the
  official Atorch "E_Test" Android app, which reads `u16(0x17,0x18)` as
  the hour field and displays `HH:MM:SS` with no days component.

### Added
- Golden regression vector `test_decode_frame_with_high_hours_byte_set`
  pinning raw bytes with a nonzero hours high byte (`0x17`=4), which
  fails under the old days/hours decode and passes under the 16-bit-hours
  decode. The round-trip fixtures could not have caught this because the
  fixture builder shared the decoder's (wrong) layout assumption.

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
