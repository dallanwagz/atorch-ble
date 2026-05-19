"""Test package for ``atorch_ble``.

Marking ``tests/`` as a package lets test modules import the shared
fixture helpers from ``tests.fixtures.known_frames`` under
``mypy --strict``. Without an ``__init__.py``, mypy treats each test
file as a top-level module and rejects relative-style cross-test
imports.
"""
