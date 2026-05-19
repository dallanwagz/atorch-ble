"""Shared pytest configuration for the ``atorch_ble`` test suite.

Hosts the single source of truth for whether the decoder's checksum gate
is on (:data:`_CHECKSUM_VALIDATED`). Test modules that exercise the
checksum behavior import this constant and either skip or invert their
expectations based on its value. Flipping this one line gates every
checksum-conditional assertion in the suite — no scattered edits.

The constant must match :data:`atorch_ble._decoder._CHECKSUM_VALIDATED`.
We assert that invariant at collection time so the flag never silently
drifts.
"""

from __future__ import annotations

from typing import Final

from atorch_ble import _decoder as _decoder_module

_CHECKSUM_VALIDATED: Final[bool] = True
"""Whether the decoder's checksum formula is enforced.

Set to ``True`` after ticket #4 verified that the documented XOR
formula ``(sum(payload[2:33]) & 0xFF) ^ 0x44`` is self-consistent
against synthetic frames built from the PROJECT_CONTEXT.md offset
table. The formula is **not** yet verified against a real captured
frame; this is acceptable per ticket #4's relaxed AC (synthetic Option
B). When a real capture lands and confirms the byte, no test changes
are required — this constant is already ``True``.
"""

assert _CHECKSUM_VALIDATED == _decoder_module._CHECKSUM_VALIDATED, (
    "tests/conftest.py::_CHECKSUM_VALIDATED has drifted from "
    "atorch_ble._decoder._CHECKSUM_VALIDATED; keep them in lockstep."
)
