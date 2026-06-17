"""Differential test del primo pezzo del transport nativo: HonDevice.

Confronta il payload del NOSTRO `client/transport/device.HonDevice` (riscritto)
con quello del `HonDevice` REALE di pyhОn, per provare che la riscrittura è
behavior-preserving (il "chi sono" inviato al cloud non cambia).

pyhon device.py + const.py sono PURI (niente aiohttp), ma importarli per via
normale farebbe girare pyhon/__init__ (→ mqtt → awscrt). Quindi li carichiamo in
un SUBPROCESS isolato con importlib, pre-registrando package vuoti per saltare
gli __init__: zero dipendenze pesanti, zero inquinamento del processo pytest, e
gira in CI senza skip.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_OUR_DEVICE = _ROOT / "custom_components" / "addhon" / "client" / "transport" / "device.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Registrare in sys.modules PRIMA di exec: con `from __future__ import
    # annotations` il @dataclass risolve le annotazioni via sys.modules[__module__].
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _pyhon_device_payloads() -> dict:
    """Esegue in subprocess: carica il HonDevice reale di pyhОn e ne ritorna i
    payload .get() per i casi di test (JSON)."""
    script = textwrap.dedent(
        f"""
        import sys, types, importlib.util, json
        from pathlib import Path
        root = Path({str(_ROOT)!r})
        pk = "custom_components.addhon._vendor.pyhon"
        for name in ("custom_components", "custom_components.addhon",
                     "custom_components.addhon._vendor", pk, pk + ".connection"):
            m = types.ModuleType(name)
            m.__path__ = [str(root / name.replace(".", "/"))]
            sys.modules[name] = m

        def load(modname, rel):
            spec = importlib.util.spec_from_file_location(modname, root / rel)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[modname] = mod
            spec.loader.exec_module(mod)
            return mod

        const = load(pk + ".const", "custom_components/addhon/_vendor/pyhon/const.py")
        sys.modules[pk].const = const  # `from ...pyhon import const` lo trova
        device = load(pk + ".connection.device",
                      "custom_components/addhon/_vendor/pyhon/connection/device.py")
        D = device.HonDevice
        out = {{
            "default": D().get(False),
            "default_mobile": D().get(True),
            "custom": D("ABC123").get(False),
            "custom_mobile": D("ABC123").get(True),
        }}
        print(json.dumps(out))
        """
    )
    res = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
    )
    if res.returncode != 0:
        raise AssertionError(f"subprocess pyhon HonDevice fallito:\n{res.stderr}")
    return json.loads(res.stdout)


class TransportDeviceDifferentialTest(unittest.TestCase):
    def setUp(self) -> None:
        self.our = _load(_OUR_DEVICE, "addhon_transport_device").HonDevice

    def test_payload_matches_pyhon(self) -> None:
        ref = _pyhon_device_payloads()
        self.assertEqual(self.our().payload(False), ref["default"])
        self.assertEqual(self.our().payload(True), ref["default_mobile"])
        self.assertEqual(self.our("ABC123").payload(False), ref["custom"])
        self.assertEqual(self.our("ABC123").payload(True), ref["custom_mobile"])

    def test_pinned_shape(self) -> None:
        # Caratterizzazione esplicita (documenta il payload e fissa i valori).
        self.assertEqual(
            self.our().payload(False),
            {
                "appVersion": "2.6.5",
                "mobileId": "pyhOn",
                "os": "android",
                "osVersion": 999,
                "deviceModel": "pyhOn",
            },
        )
        # mobile=True: 'os' diventa 'mobileOs', niente più 'os'.
        mobile = self.our().payload(True)
        self.assertNotIn("os", mobile)
        self.assertEqual(mobile["mobileOs"], "android")

    def test_empty_mobile_id_falls_back_to_default(self) -> None:
        self.assertEqual(self.our("").mobile_id, "pyhOn")


if __name__ == "__main__":
    unittest.main()
