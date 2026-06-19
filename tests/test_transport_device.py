"""Test of the native device descriptor: `client/transport/device.HonDevice`.

Originally a DIFFERENTIAL test against pyhOn's real `HonDevice` (loaded in a
subprocess). In piece 4b the pyhOn transport (`_vendor/connection/device.py`) was
DELETED: the oracle no longer exists. The expected values below ARE the contract
(they were byte-identical to pyhOn, validated by the differential before the
cutover): now we pin the cloud payload directly.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_OUR_DEVICE = _ROOT / "custom_components" / "addhon" / "client" / "transport" / "device.py"

# Device payload contract towards the hOn cloud (ex-pyhOn oracle, now frozen).
_DEFAULT = {
    "appVersion": "2.6.5",
    "mobileId": "pyhOn",
    "os": "android",
    "osVersion": 999,
    "deviceModel": "pyhOn",
}
_DEFAULT_MOBILE = {
    "appVersion": "2.6.5",
    "mobileId": "pyhOn",
    "osVersion": 999,
    "deviceModel": "pyhOn",
    "mobileOs": "android",
}
_CUSTOM = {**_DEFAULT, "mobileId": "ABC123"}
_CUSTOM_MOBILE = {**_DEFAULT_MOBILE, "mobileId": "ABC123"}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec: with `from __future__ import
    # annotations` the @dataclass resolves the annotations via sys.modules[__module__].
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TransportDeviceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.our = _load(_OUR_DEVICE, "addhon_transport_device").HonDevice

    def test_payload_matches_frozen_contract(self) -> None:
        self.assertEqual(self.our().payload(False), _DEFAULT)
        self.assertEqual(self.our().payload(True), _DEFAULT_MOBILE)
        self.assertEqual(self.our("ABC123").payload(False), _CUSTOM)
        self.assertEqual(self.our("ABC123").payload(True), _CUSTOM_MOBILE)

    def test_mobile_renames_os(self) -> None:
        mobile = self.our().payload(True)
        self.assertNotIn("os", mobile)
        self.assertEqual(mobile["mobileOs"], "android")

    def test_empty_mobile_id_falls_back_to_default(self) -> None:
        self.assertEqual(self.our("").mobile_id, "pyhOn")


if __name__ == "__main__":
    unittest.main()
