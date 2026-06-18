"""Golden test del ROOT appliance nativo (Fase 4). Congela proprietà + load end-to-end
sul dump reale del frigo. Era differential vs pyhОn (slice 5a); con `_vendor/` cancellato
è golden (output nativo provato == pyhОn al checkpoint 5a, commit 520f036).
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _golden import REPO, frozen, install_stubs, normalize  # noqa: E402

install_stubs()
_DUMP = REPO / "apk" / "dump" / "ref_10136"

from custom_components.addhon.client import pyhon_adapter  # noqa: E402

NaRoot = pyhon_adapter._native_engine_appliance_cls()


def _load(name: str):
    return json.loads((_DUMP / name).read_text(encoding="utf-8"))


class FakeApi:
    async def load_commands(self, a):
        return _load("commands.json")

    async def load_favourites(self, a):
        return []

    async def load_command_history(self, a):
        return _load("command_history.json")

    async def load_attributes(self, a):
        return _load("attributes.json")

    async def load_statistics(self, a):
        return _load("statistics.json")

    async def load_maintenance(self, a):
        return _load("maintenance.json")


_INFO = {
    "applianceTypeName": "REF", "applianceModelId": "10136",
    "macAddress": "11-22-33-44-55-66", "modelName": "HDPW5620CNPK", "brand": "haier",
    "nickName": "Frigo", "code": "ABC123", "serialNumber": "0123456789",
    "attributes": [{"parName": "a", "parValue": "1"}, {"parName": "b", "parValue": "2"}],
}

_PROPS = ["appliance_type", "appliance_model_id", "mac_address", "unique_id", "model_name",
          "brand", "nick_name", "code", "model_id", "zone", "connection"]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _snap_param(p):
    s = {"value": p.value, "intern_value": p.intern_value, "values": list(p.values)}
    if hasattr(p, "min"):
        s["min"], s["max"], s["step"] = p.min, p.max, p.step
    return s


def _native_snapshot():
    out = {"props": {}}
    for zone in (0, 1, 2):
        app = NaRoot(FakeApi(), json.loads(json.dumps(_INFO)), zone=zone)
        out["props"][str(zone)] = {p: getattr(app, p) for p in _PROPS}
    app0 = NaRoot(FakeApi(), json.loads(json.dumps(_INFO)), zone=0)
    out["info_attributes"] = app0.info["attributes"]
    # load end-to-end
    app = NaRoot(FakeApi(), json.loads(json.dumps(_INFO)), zone=0)
    _run(app.load_commands())
    _run(app.load_attributes())
    _run(app.load_statistics())
    out["commands"] = sorted(app.commands)
    out["available_settings"] = sorted(app.available_settings)
    out["options"] = app.options
    out["additional_data"] = sorted(app.additional_data)
    out["settings"] = {k: _snap_param(v) for k, v in sorted(app.settings.items())}
    out["statistics"] = app.statistics
    out["attr_param_keys"] = sorted(app.attributes.get("parameters", {}))
    out["programName"] = app.attributes.get("programName")
    out["available"] = app.attributes.get("available")
    out["command_parameters"] = app.command_parameters
    out["data_keys"] = sorted(app.data)
    return out


class RootGoldenTest(unittest.TestCase):
    def test_native_root_matches_golden(self) -> None:
        snap = _native_snapshot()
        self.assertEqual(normalize(snap), frozen("engine_appliance_root", snap))

    def test_info_attributes_parsed(self) -> None:
        app = NaRoot(FakeApi(), json.loads(json.dumps(_INFO)), zone=0)
        self.assertEqual(app.info["attributes"], {"a": "1", "b": "2"})

    def test_root_module_is_native(self) -> None:
        self.assertEqual(NaRoot.__module__, "custom_components.addhon.client.engine.appliance")


if __name__ == "__main__":
    unittest.main()
