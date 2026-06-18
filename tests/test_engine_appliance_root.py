"""Differential del ROOT appliance NATIVO (Fase 4 slice 5) vs pyhОn.

Copre la superficie del ROOT che i test cluster/per-tipo non toccano: le proprietà
identificative (mac/unique_id/model/brand/nick/code/model_id/type/zone), il parsing di
`info["attributes"]`, e load_commands/load_attributes/load_statistics end-to-end sul
dump reale del frigo (settings/available_settings/data/command_parameters/attributi).
Oracolo = `_vendor.pyhon.appliance.HonAppliance` (ultimo confronto prima di cancellare
`_vendor` allo slice 5b). HA/aiohttp/yarl stubati.
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
_DUMP = REPO / "apk" / "dump" / "ref_10136"


def _mod(name: str) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        sys.modules[name] = m
    return m


def _install_stubs() -> None:
    ce = _mod("homeassistant.config_entries")
    ce.ConfigEntry = getattr(ce, "ConfigEntry", type("ConfigEntry", (), {}))
    core = _mod("homeassistant.core")
    core.HomeAssistant = getattr(core, "HomeAssistant", type("HomeAssistant", (), {}))
    exc = _mod("homeassistant.exceptions")
    base = getattr(exc, "HomeAssistantError", type("HomeAssistantError", (Exception,), {}))
    exc.HomeAssistantError = base
    exc.ConfigEntryNotReady = getattr(exc, "ConfigEntryNotReady", type("ConfigEntryNotReady", (base,), {}))
    exc.ConfigEntryAuthFailed = getattr(exc, "ConfigEntryAuthFailed", type("ConfigEntryAuthFailed", (base,), {}))
    uc = _mod("homeassistant.helpers.update_coordinator")
    uc.DataUpdateCoordinator = getattr(uc, "DataUpdateCoordinator", type("DataUpdateCoordinator", (), {}))
    uc.UpdateFailed = getattr(uc, "UpdateFailed", type("UpdateFailed", (Exception,), {}))
    ha = _mod("homeassistant")
    ha.config_entries, ha.core, ha.exceptions = ce, core, exc
    ha.helpers = _mod("homeassistant.helpers")
    ha.helpers.update_coordinator = uc
    yarl = _mod("yarl")
    if not hasattr(yarl, "URL"):
        yarl.URL = type("URL", (), {"__init__": lambda self, s, encoded=False: None})
    aio = _mod("aiohttp")
    aio.ClientSession = getattr(aio, "ClientSession", type("ClientSession", (), {}))
    aio.ClientResponse = getattr(aio, "ClientResponse", type("ClientResponse", (), {}))
    aio.ContentTypeError = getattr(aio, "ContentTypeError", type("ContentTypeError", (Exception,), {}))
    aio.client = _mod("aiohttp.client")
    aio.client._RequestContextManager = type("_RCM", (), {})


_install_stubs()

from custom_components.addhon.client import pyhon_adapter  # noqa: E402

pyhon_adapter.ensure_enum_patch()
from custom_components.addhon._vendor.pyhon.appliance import HonAppliance as PyRoot  # noqa: E402

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
    "applianceTypeName": "REF",
    "applianceModelId": "10136",
    "macAddress": "11-22-33-44-55-66",
    "modelName": "HDPW5620CNPK",
    "brand": "haier",
    "nickName": "Frigo",
    "code": "ABC123",
    "serialNumber": "0123456789",
    "attributes": [{"parName": "a", "parValue": "1"}, {"parName": "b", "parValue": "2"}],
}

_PROPS = [
    "appliance_type", "appliance_model_id", "mac_address", "unique_id", "model_name",
    "brand", "nick_name", "code", "model_id", "zone", "connection",
]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class RootPropertiesTest(unittest.TestCase):
    def _pair(self, zone=0):
        py = PyRoot(FakeApi(), json.loads(json.dumps(_INFO)), zone=zone)
        na = NaRoot(FakeApi(), json.loads(json.dumps(_INFO)), zone=zone)
        return py, na

    def test_properties_parity(self) -> None:
        for zone in (0, 1, 2):
            py, na = self._pair(zone=zone)
            for prop in _PROPS:
                with self.subTest(zone=zone, prop=prop):
                    self.assertEqual(getattr(na, prop), getattr(py, prop))

    def test_info_attributes_parsed(self) -> None:
        py, na = self._pair()
        self.assertEqual(na.info["attributes"], {"a": "1", "b": "2"})
        self.assertEqual(na.info["attributes"], py.info["attributes"])

    def test_native_root_not_pyhon_subclass(self) -> None:
        self.assertFalse(issubclass(NaRoot, PyRoot))


class RootLoadParityTest(unittest.TestCase):
    def _built(self, cls):
        app = cls(FakeApi(), json.loads(json.dumps(_INFO)), zone=0)
        _run(app.load_commands())
        _run(app.load_attributes())
        _run(app.load_statistics())
        return app

    def _snap_param(self, p):
        s = {"value": p.value, "intern_value": p.intern_value, "values": list(p.values)}
        if hasattr(p, "min"):
            s["min"], s["max"], s["step"] = p.min, p.max, p.step
        return s

    def test_load_endtoend_parity(self) -> None:
        py = self._built(PyRoot)
        na = self._built(NaRoot)
        self.assertEqual(sorted(na.commands), sorted(py.commands))
        self.assertEqual(sorted(na.available_settings), sorted(py.available_settings))
        self.assertEqual(na.options, py.options)
        self.assertEqual(sorted(na.additional_data), sorted(py.additional_data))
        # settings (param) parità
        na_s = {k: self._snap_param(v) for k, v in sorted(na.settings.items())}
        py_s = {k: self._snap_param(v) for k, v in sorted(py.settings.items())}
        self.assertEqual(na_s, py_s)
        # statistics + attributi (shadow) chiavi + programName
        self.assertEqual(na.statistics, py.statistics)
        self.assertEqual(sorted(na.attributes.get("parameters", {})), sorted(py.attributes.get("parameters", {})))
        self.assertEqual(na.attributes.get("programName"), py.attributes.get("programName"))
        self.assertEqual(na.command_parameters, py.command_parameters)

    def test_data_property_parity(self) -> None:
        py = self._built(PyRoot)
        na = self._built(NaRoot)
        # `data` mescola attributi+command_parameters. UNICA differenza top-level: il
        # nativo aggiunge `available` (campo first-class modellato sull'app, documentato).
        self.assertEqual(set(na.data) - set(py.data), {"available"})
        self.assertEqual(set(py.data) - set(na.data), set())


if __name__ == "__main__":
    unittest.main()
