"""Test del descrittore device nativo: `client/transport/device.HonDevice`.

In origine era un DIFFERENTIAL test contro il `HonDevice` reale di pyhOn (caricato
in subprocess). Nel piece 4b il transport pyhOn (`_vendor/connection/device.py`) è
stato CANCELLATO: l'oracolo non esiste più. I valori attesi qui sotto SONO il
contratto (erano byte-identici a pyhOn, validati dal differential prima del
cutover): ora pinniamo direttamente il payload del cloud.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_OUR_DEVICE = _ROOT / "custom_components" / "addhon" / "client" / "transport" / "device.py"

# Contratto del payload device verso il cloud hOn (ex-oracolo pyhOn, ora congelato).
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
    # Registrare in sys.modules PRIMA di exec: con `from __future__ import
    # annotations` il @dataclass risolve le annotazioni via sys.modules[__module__].
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
