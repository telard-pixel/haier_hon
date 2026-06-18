"""Differential test del CLUSTER motore nativo (Fase 4 slice 3) vs pyhОn.

Cluster = commands + command_loader + rules + program (+ i parametri dello slice 1).
Oracolo = lo stesso motore di pyhОn CON la patch BABYCARE (comportamento di
PRODUZIONE). L'appliance "oracolo" è il `HonAppliance` di pyhОn puro; l'appliance
"nativa" è quella della factory `pyhon_adapter._native_engine_appliance_cls()`
(sottoclasse col loader/commands NATIVI iniettati). NB: il FLIP in produzione è
RIMANDATO (`create_appliance` ritorna ancora il ROOT pyhОn finché le per-tipo `_extra`
non sono native, slice 4), quindi questa sottoclasse è esercitata SOLO da qui. Le due
differiscono SOLO in `load_commands` e `sync_params_to_command`: tutto il resto del
ROOT è condiviso, quindi il diff isola esattamente il flip del cluster.

Parte A — end-to-end sui dati REALI del frigo (commands.json + command_history.json):
  costruzione comandi/parametri/categorie/program + recover ultimo stato + sync con
  lo shadow. Copre TUTTO tranne le rules (il frigo non ne ha).
Parte B — send-path: assemblaggio identico di (name, params, ancillary, category),
  incluso pop di programRules e prStr.
Parte C — RULES su fixture SINTETICHE (il frigo non ha rules e l'AC è offline):
  native HonCommand vs pyhОn HonCommand, stesso input, stesso stato del target dopo
  il trigger. NB: parità con pyhОn, NON col modello `programRules` dell'app (rimandato
  a live-AC, vedi engine/rules.py).
Parte D — conformità ai Protocol di interfaces.py.

HA/aiohttp/yarl stubati (il motore importa senza awscrt; l'appliance pyhОn importa
typedefs->aiohttp/yarl e il package->homeassistant).
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

from custom_components.addhon._vendor.pyhon.appliance import HonAppliance as PyAppliance  # noqa: E402
from custom_components.addhon._vendor.pyhon.commands import HonCommand as PyCommand  # noqa: E402
from custom_components.addhon.client.engine.commands import HonCommand as NaCommand  # noqa: E402
from custom_components.addhon.client import interfaces  # noqa: E402


def _load(name: str):
    return json.loads((_DUMP / name).read_text(encoding="utf-8"))


class FakeApi:
    """api fittizia che restituisce i dump reali; registra send_command."""

    def __init__(self, *, favourites=None) -> None:
        self.sent: list = []
        self._favourites = favourites or []

    async def load_commands(self, appliance):
        return _load("commands.json")

    async def load_favourites(self, appliance):
        return list(self._favourites)

    async def load_command_history(self, appliance):
        return _load("command_history.json")

    async def load_attributes(self, appliance):
        return _load("attributes.json")

    async def load_statistics(self, appliance):
        return _load("statistics.json")

    async def load_maintenance(self, appliance):
        return _load("maintenance.json")

    async def send_command(self, appliance, name, params, ancillary, category):
        self.sent.append((name, dict(params), dict(ancillary), category))
        return True


_INFO = {"applianceTypeName": "REF", "applianceModelId": 10136, "macAddress": "aa-bb"}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _snap_param(p) -> dict:
    s = {
        "key": p.key,
        "category": p.category,
        "typology": p.typology,
        "mandatory": p.mandatory,
        "group": p.group,
        "value": p.value,
        "intern_value": p.intern_value,
        "values": list(p.values),
    }
    if hasattr(p, "min") and hasattr(p, "max") and hasattr(p, "step"):
        s["min"], s["max"], s["step"] = p.min, p.max, p.step
    if hasattr(p, "ids"):  # HonParameterProgram: la mappa prCode->programma
        try:
            s["ids"] = dict(p.ids)
        except Exception as e:  # stessa rappresentazione su entrambi i motori
            s["ids"] = f"<{type(e).__name__}>"
    if hasattr(p, "triggers"):  # rules agganciate a questo parametro
        s["triggers"] = p.triggers
    return s


def _snap_command(c) -> dict:
    return {
        "name": c.name,
        "category": c.category,
        "setting_keys": sorted(c.setting_keys),
        "categories": sorted(c.categories),
        "parameters": {k: _snap_param(p) for k, p in sorted(c.parameters.items())},
        "parameter_value": c.parameter_value,
        "parameter_groups": c.parameter_groups,
        "mandatory_parameter_groups": c.mandatory_parameter_groups,
        "available_settings": {
            k: _snap_param(p) for k, p in sorted(c.available_settings.items())
        },
        "data_keys": sorted(c.data),
    }


def _snap_appliance(a) -> dict:
    return {
        "commands": {n: _snap_command(c) for n, c in sorted(a.commands.items())},
        "additional_data_keys": sorted(a.additional_data),
        "options": a.options,
        "available_settings": sorted(a.available_settings),
        "settings": {k: _snap_param(p) for k, p in sorted(a.settings.items())},
        "command_parameters": a.command_parameters,
    }


class ClusterEndToEndTest(unittest.TestCase):
    """Parte A: load_commands + sync sullo shadow, sui dati reali del frigo."""

    def _build(self, cls, api):
        appliance = cls(api, dict(_INFO), zone=0)
        _run(appliance.load_commands())
        return appliance

    def test_load_commands_parity(self) -> None:
        py = self._build(PyAppliance, FakeApi())
        na = self._build(pyhon_adapter._native_engine_appliance_cls(), FakeApi())
        self.assertEqual(_snap_appliance(na), _snap_appliance(py))

    def test_sync_after_attributes_parity(self) -> None:
        py = self._build(PyAppliance, FakeApi())
        na = self._build(pyhon_adapter._native_engine_appliance_cls(), FakeApi())
        _run(py.load_attributes())
        _run(na.load_attributes())
        py.sync_params_to_command("settings")
        na.sync_params_to_command("settings")
        self.assertEqual(_snap_appliance(na), _snap_appliance(py))

    def test_native_appliance_is_standalone_root(self) -> None:
        # slice 5: il ROOT nativo è standalone, NON più sottoclasse del ROOT pyhОn
        self.assertFalse(issubclass(pyhon_adapter._native_engine_appliance_cls(), PyAppliance))


class SendPathParityTest(unittest.TestCase):
    """Parte B: assemblaggio del comando da inviare identico."""

    def test_send_assembles_same_request(self) -> None:
        for cmd_name in ("settings",):
            py_api, na_api = FakeApi(), FakeApi()
            py = PyAppliance(py_api, dict(_INFO), zone=0)
            na = pyhon_adapter._native_engine_appliance_cls()(na_api, dict(_INFO), zone=0)
            _run(py.load_commands())
            _run(na.load_commands())
            _run(py.load_attributes())
            _run(na.load_attributes())
            _run(py.commands[cmd_name].send())
            _run(na.commands[cmd_name].send())
            self.assertEqual(na_api.sent, py_api.sent)
            self.assertTrue(na_api.sent, "nessun send registrato")


class DictApi:
    """api fittizia su dict in-memory (per scenari che il dump frigo non copre:
    favourites, multi-programma con prCode, prStr/programRules, recover-program).
    Ogni load ritorna una COPIA profonda (i due motori non condividono/mutano lo
    stesso dict)."""

    def __init__(self, commands, history=None, favourites=None, attributes=None) -> None:
        self.sent: list = []
        self._commands = commands
        self._history = history or []
        self._favourites = favourites or []
        self._attributes = attributes or {"shadow": {"parameters": {}}}

    async def load_commands(self, a):
        return json.loads(json.dumps(self._commands))

    async def load_favourites(self, a):
        return json.loads(json.dumps(self._favourites))

    async def load_command_history(self, a):
        return json.loads(json.dumps(self._history))

    async def load_attributes(self, a):
        return json.loads(json.dumps(self._attributes))

    async def load_statistics(self, a):
        return {}

    async def load_maintenance(self, a):
        return {}

    async def send_command(self, a, name, params, ancillary, category):
        self.sent.append((name, dict(params), dict(ancillary), category))
        return True


def _prog(pr_code: str) -> dict:
    return {
        "description": "d", "protocolType": "MQTT",
        "parameters": {
            "prCode": {"typology": "fixed", "category": "command", "mandatory": 1, "fixedValue": pr_code},
            "prStr": {"typology": "fixed", "category": "command", "mandatory": 1, "fixedValue": "x"},
            "tempSel": {"typology": "range", "category": "command", "mandatory": 0,
                        "defaultValue": "5", "minimumValue": "2", "maximumValue": "8", "incrementValue": "1"},
        },
    }


_RICH_COMMANDS = {
    "applianceModel": {"options": {}},
    "settings": {
        "setParameters": {
            "description": "d", "protocolType": "MQTT",
            "parameters": {
                "tempSel": {"typology": "range", "category": "command", "mandatory": 1,
                            "defaultValue": "5", "minimumValue": "2", "maximumValue": "8", "incrementValue": "1"},
            },
        },
    },
    "startProgram": {
        "PROGRAMS.REF.SUPER_COOL": {
            **_prog("1"),
            "ancillaryParameters": {
                "programRules": {"typology": "fixed", "category": "command", "mandatory": 0, "fixedValue": "0"},
                "remoteActionable": {"typology": "fixed", "category": "command", "mandatory": 0, "fixedValue": "1"},
            },
        },
        "PROGRAMS.REF.SUPER_FREEZE": _prog("5"),
        "PROGRAMS.REF.iot_auto": {
            "description": "d", "protocolType": "MQTT",
            "parameters": {
                "prCode": {"typology": "fixed", "category": "command", "mandatory": 1, "fixedValue": "9"},
            },
        },
    },
    "stopProgram": {
        "description": "d", "protocolType": "MQTT",
        "parameters": {"onOff": {"typology": "fixed", "category": "command", "mandatory": 1, "fixedValue": "0"}},
    },
    "dictionaryId": 1,
}

# `speed` con TIPO diverso tra due programmi: esercita il ramo Fixed-first/non-Fixed
# di `_more_options` (available_settings sceglie il non-Fixed).
_RICH_COMMANDS["startProgram"]["PROGRAMS.REF.SUPER_COOL"]["parameters"]["speed"] = {
    "typology": "fixed", "category": "command", "mandatory": 0, "fixedValue": "3"}
_RICH_COMMANDS["startProgram"]["PROGRAMS.REF.SUPER_FREEZE"]["parameters"]["speed"] = {
    "typology": "range", "category": "command", "mandatory": 0,
    "defaultValue": "3", "minimumValue": "1", "maximumValue": "5", "incrementValue": "1"}

# Programmi dichiarati FUORI ordine prCode + un nome mixed-case: per fissare in modo
# order-sensitive l'ordinamento di `ids` e l'upper-case di `prStr`.
_IDS_ORDER_COMMANDS = {
    "applianceModel": {"options": {}},
    "startProgram": {
        "PROGRAMS.REF.BIG": _prog("9"),
        "PROGRAMS.REF.SMALL": _prog("1"),
    },
    "dictionaryId": 1,
}
_MIXEDCASE_COMMANDS = {
    "applianceModel": {"options": {}},
    "startProgram": {"PROGRAMS.REF.Mixed_Case": _prog("1")},
    "dictionaryId": 1,
}

_RICH_FAVOURITES = [{
    "favouriteName": "MyFav",
    "command": {"commandName": "startProgram", "programName": "PROGRAMS.REF.SUPER_COOL"},
    "parameters": {"tempSel": "7"},
}]

# command-history che esercita il recover del PROGRAMMA (pop "program") + un valore
# non-default su un parametro non-fixed (tempSel) -> kill dei mutanti di recover.
_RICH_HISTORY = [{
    "command": {
        "commandName": "startProgram",
        "parameters": {"program": "PROGRAMS.REF.SUPER_FREEZE", "tempSel": "7"},
    },
}]


class RichClusterParityTest(unittest.TestCase):
    """Scenari che il dump frigo non copre: favourites, multi-programma con prCode/
    ids, prStr/programRules sul send-path, recover-program, zone>0, selezione
    programma a runtime. Tutto diffato native vs pyhОn su input identici."""

    def _pair(self, **api_kw):
        py_api = DictApi(_RICH_COMMANDS, **api_kw)
        na_api = DictApi(_RICH_COMMANDS, **api_kw)
        py = PyAppliance(py_api, dict(_INFO), zone=0)
        na = pyhon_adapter._native_engine_appliance_cls()(na_api, dict(_INFO), zone=0)
        _run(py.load_commands())
        _run(na.load_commands())
        return py, na, py_api, na_api

    def test_multiprogram_load_and_ids_parity(self) -> None:
        py, na, *_ = self._pair()
        self.assertEqual(_snap_appliance(na), _snap_appliance(py))
        # sanity: gli ids escludono iot_ e mappano prCode->programma
        prog = na.commands["startProgram"].parameters["program"]
        self.assertEqual(prog.ids, {1: "super_cool", 5: "super_freeze"})

    def test_favourites_parity(self) -> None:
        py, na, *_ = self._pair(favourites=_RICH_FAVOURITES)
        self.assertEqual(_snap_appliance(na), _snap_appliance(py))
        self.assertIn("MyFav", na.commands["startProgram"].categories)

    def test_recover_program_parity(self) -> None:
        py, na, *_ = self._pair(history=_RICH_HISTORY)
        self.assertEqual(_snap_appliance(na), _snap_appliance(py))

    def test_zone1_parity(self) -> None:
        py_api, na_api = DictApi(_RICH_COMMANDS), DictApi(_RICH_COMMANDS)
        py = PyAppliance(py_api, dict(_INFO), zone=1)
        na = pyhon_adapter._native_engine_appliance_cls()(na_api, dict(_INFO), zone=1)
        _run(py.load_commands())
        _run(na.load_commands())
        self.assertEqual(_snap_appliance(na), _snap_appliance(py))

    def test_send_startprogram_prstr_and_programrules(self) -> None:
        py, na, py_api, na_api = self._pair()
        _run(py.commands["startProgram"].send())
        _run(na.commands["startProgram"].send())
        self.assertEqual(na_api.sent, py_api.sent)
        name, params, ancillary, _ = na_api.sent[0]
        self.assertEqual(params["prStr"], "PROGRAMS.REF.SUPER_COOL")  # prStr -> categoria upper
        self.assertNotIn("programRules", ancillary)  # programRules rimosso

    def test_send_only_mandatory_parity(self) -> None:
        py, na, py_api, na_api = self._pair()
        _run(py.commands["startProgram"].send(only_mandatory=True))
        _run(na.commands["startProgram"].send(only_mandatory=True))
        self.assertEqual(na_api.sent, py_api.sent)

    def test_send_specific_parity(self) -> None:
        py, na, py_api, na_api = self._pair()
        _run(py.commands["startProgram"].send_specific(["tempSel"]))
        _run(na.commands["startProgram"].send_specific(["tempSel"]))
        self.assertEqual(na_api.sent, py_api.sent)

    def test_program_selection_runtime_parity(self) -> None:
        # selezione programma a runtime: cambia il comando attivo in appliance.commands
        py, na, *_ = self._pair()
        py.commands["startProgram"].parameters["program"].value = "super_freeze"
        na.commands["startProgram"].parameters["program"].value = "super_freeze"
        self.assertEqual(
            na.commands["startProgram"].category, py.commands["startProgram"].category
        )
        self.assertEqual(na.commands["startProgram"].category, "PROGRAMS.REF.SUPER_FREEZE")

    def test_program_value_invalid_raises(self) -> None:
        py, na, *_ = self._pair()
        with self.assertRaises(ValueError):
            py.commands["startProgram"].parameters["program"].value = "nope"
        with self.assertRaises(ValueError):
            na.commands["startProgram"].parameters["program"].value = "nope"

    def test_ids_sorted_order_sensitive(self) -> None:
        # programmi dichiarati 9-poi-1: `ids` deve risultare ORDINATO per prCode
        py_api, na_api = DictApi(_IDS_ORDER_COMMANDS), DictApi(_IDS_ORDER_COMMANDS)
        py = PyAppliance(py_api, dict(_INFO), zone=0)
        na = pyhon_adapter._native_engine_appliance_cls()(na_api, dict(_INFO), zone=0)
        _run(py.load_commands())
        _run(na.load_commands())
        na_ids = list(na.commands["startProgram"].parameters["program"].ids.items())
        py_ids = list(py.commands["startProgram"].parameters["program"].ids.items())
        self.assertEqual(na_ids, py_ids)
        self.assertEqual(na_ids, [(1, "small"), (9, "big")])  # ordine, non solo set

    def test_prstr_uppercased_mixed_case_key(self) -> None:
        py_api, na_api = DictApi(_MIXEDCASE_COMMANDS), DictApi(_MIXEDCASE_COMMANDS)
        py = PyAppliance(py_api, dict(_INFO), zone=0)
        na = pyhon_adapter._native_engine_appliance_cls()(na_api, dict(_INFO), zone=0)
        _run(py.load_commands())
        _run(na.load_commands())
        _run(py.commands["startProgram"].send())
        _run(na.commands["startProgram"].send())
        self.assertEqual(na_api.sent, py_api.sent)
        self.assertEqual(na_api.sent[0][1]["prStr"], "PROGRAMS.REF.MIXED_CASE")


class FakeAppliance:
    """Appliance minimale per costruire un HonCommand isolato (test rules)."""

    def __init__(self) -> None:
        self.zone = 0
        self.options: dict = {}
        self.commands: dict = {}


# Fixture sintetiche: ogni rule lega un trigger (mode) a un target.
_RULE_FIXED_RANGE_IN = {
    "parameters": {
        "mode": {"typology": "enum", "category": "command", "mandatory": 1,
                 "defaultValue": "cold", "enumValues": ["cold", "hot"]},
        "temp": {"typology": "range", "category": "command", "mandatory": 0,
                 "defaultValue": "20", "minimumValue": "10", "maximumValue": "40",
                 "incrementValue": "1"},
    },
    "rules": {
        "tempRule": {"category": "rule",
                     "fixedValue": {"temp": {"mode": {"hot": {"typology": "fixed", "fixedValue": "30"}}}}},
    },
}
_RULE_FIXED_RANGE_EXPAND = {
    "parameters": {
        "mode": {"typology": "enum", "category": "command", "mandatory": 1,
                 "defaultValue": "cold", "enumValues": ["cold", "hot"]},
        "temp": {"typology": "range", "category": "command", "mandatory": 0,
                 "defaultValue": "20", "minimumValue": "10", "maximumValue": "40",
                 "incrementValue": "1"},
    },
    "rules": {
        "tempRule": {"category": "rule",
                     "fixedValue": {"temp": {"mode": {"hot": {"typology": "fixed", "fixedValue": "55"}}}}},
    },
}
_RULE_ENUM_TARGET = {
    "parameters": {
        "mode": {"typology": "enum", "category": "command", "mandatory": 1,
                 "defaultValue": "cold", "enumValues": ["cold", "hot"]},
        "fan": {"typology": "enum", "category": "command", "mandatory": 0,
                "defaultValue": "low", "enumValues": ["low", "mid", "high"]},
    },
    "rules": {
        "fanRule": {"category": "rule",
                    "enumValues": {"fan": {"mode": {"hot": {"typology": "enum",
                                                           "enumValues": "mid|high",
                                                           "defaultValue": "high"}}}}},
    },
}


def _enum(default, values):
    return {"typology": "enum", "category": "command", "mandatory": 0,
            "defaultValue": default, "enumValues": values}


def _range(default="20", lo="10", hi="40", inc="1"):
    return {"typology": "range", "category": "command", "mandatory": 0,
            "defaultValue": default, "minimumValue": lo, "maximumValue": hi, "incrementValue": inc}


def _rule(rule_dict, kind="fixedValue"):
    return {"category": "rule", kind: rule_dict}


# |-split: un solo trigger-value "cold|hot" -> due rules
_RULE_PIPE_SPLIT = {
    "parameters": {"mode": _enum("cold", ["cold", "hot"]), "temp": _range()},
    "rules": {"r": _rule({"temp": {"mode": {"cold|hot": {"typology": "fixed", "fixedValue": "30"}}}})},
}
# @-prefix sulla chiave trigger -> deve essere strippato a "mode"
_RULE_AT_STRIP = {
    "parameters": {"mode": _enum("cold", ["cold", "hot"]), "temp": _range()},
    "rules": {"r": _rule({"temp": {"@mode": {"hot": {"typology": "fixed", "fixedValue": "30"}}}})},
}
# self-ref @{param_key} -> _create_rule la scarta (nessun trigger)
_RULE_SELF_REF = {
    "parameters": {"mode": _enum("cold", ["cold", "hot"]), "temp": _range()},
    "rules": {"r": _rule({"temp": {"mode": {"hot": {"typology": "fixed", "fixedValue": "@temp"}}}})},
}
# shorthand: param_data scalare (non-dict) -> {"typology":"fixed","fixedValue":scalar}
_RULE_SCALAR = {
    "parameters": {"mode": _enum("cold", ["cold", "hot"]), "temp": _range()},
    "rules": {"r": _rule({"temp": {"mode": {"hot": "30"}}})},
}
# fixedValue su target ENUM -> _apply_fixed ramo enum (values=[v])
_RULE_FIXED_ON_ENUM = {
    "parameters": {"mode": _enum("cold", ["cold", "hot"]), "fan": _enum("low", ["low", "mid", "high"])},
    "rules": {"r": _rule({"fan": {"mode": {"hot": {"typology": "fixed", "fixedValue": "high"}}}})},
}
# fixedValue < min -> _apply_fixed abbassa il min
_RULE_RANGE_SHRINK = {
    "parameters": {"mode": _enum("cold", ["cold", "hot"]), "temp": _range(default="20", lo="10")},
    "rules": {"r": _rule({"temp": {"mode": {"hot": {"typology": "fixed", "fixedValue": "5"}}}})},
}
# condizioni-extra annidate (mode=hot AND speed=hi) -> _parse_conditions ricorsivo +
# _duplicate_for_extra_conditions + _extra_rules_matches
_RULE_NESTED = {
    "parameters": {
        "mode": _enum("cold", ["cold", "hot"]),
        "speed": _enum("lo", ["lo", "hi"]),
        "temp": _range(),
    },
    "rules": {"r": _rule({"temp": {"mode": {"hot": {"speed": {"hi": {"typology": "fixed", "fixedValue": "35"}}}}}})},
}


class RulesSyntheticParityTest(unittest.TestCase):
    """Parte C: rules native == rules pyhОn su fixture sintetiche (il frigo non ha
    rules, l'AC è offline). Confronta lo snapshot COMPLETO dei parametri (incl.
    `.triggers`, dove `_duplicate_for_extra_conditions` è osservabile) prima e dopo
    ogni azione. Parità con pyhОn, NON col modello `programRules` dell'app (rimandato
    a live-AC, vedi engine/rules.py)."""

    def _both(self, attrs):
        py = PyCommand("c", json.loads(json.dumps(attrs)), FakeAppliance())
        na = NaCommand("c", json.loads(json.dumps(attrs)), FakeAppliance())
        return py, na

    def _snap_params(self, c) -> dict:
        return {k: _snap_param(p) for k, p in sorted(c.parameters.items())}

    def _assert_parity(self, attrs, actions):
        """actions = lista di (param_name, value) applicate in ordine a ENTRAMBI."""
        py, na = self._both(attrs)
        # parità a costruzione (incl. .triggers = effetto di patch/_duplicate)
        self.assertEqual(self._snap_params(na), self._snap_params(py))
        for param, value in actions:
            py.parameters[param].value = value
            na.parameters[param].value = value
            self.assertEqual(self._snap_params(na), self._snap_params(py))

    def test_fixed_rule_in_range(self) -> None:
        self._assert_parity(_RULE_FIXED_RANGE_IN, [("mode", "hot")])

    def test_fixed_rule_expands_range(self) -> None:
        self._assert_parity(_RULE_FIXED_RANGE_EXPAND, [("mode", "hot")])

    def test_enum_rule_target(self) -> None:
        self._assert_parity(_RULE_ENUM_TARGET, [("mode", "hot")])

    def test_rule_not_triggered_leaves_target(self) -> None:
        self._assert_parity(_RULE_FIXED_RANGE_IN, [("mode", "cold")])

    def test_pipe_split_trigger(self) -> None:
        self._assert_parity(_RULE_PIPE_SPLIT, [("mode", "hot")])
        self._assert_parity(_RULE_PIPE_SPLIT, [("mode", "cold")])

    def test_at_prefixed_trigger_key(self) -> None:
        self._assert_parity(_RULE_AT_STRIP, [("mode", "hot")])

    def test_self_reference_skipped(self) -> None:
        self._assert_parity(_RULE_SELF_REF, [("mode", "hot")])

    def test_scalar_shorthand_rule(self) -> None:
        self._assert_parity(_RULE_SCALAR, [("mode", "hot")])

    def test_fixed_rule_on_enum_target(self) -> None:
        self._assert_parity(_RULE_FIXED_ON_ENUM, [("mode", "hot")])

    def test_fixed_rule_shrinks_range_min(self) -> None:
        self._assert_parity(_RULE_RANGE_SHRINK, [("mode", "hot")])

    def test_nested_extra_conditions_both_met(self) -> None:
        # entrambe le condizioni: temp deve cambiare su entrambe
        self._assert_parity(_RULE_NESTED, [("speed", "hi"), ("mode", "hot")])

    def test_nested_extra_conditions_partial(self) -> None:
        # solo mode=hot (speed resta lo): _extra_rules_matches fallisce, temp invariato
        self._assert_parity(_RULE_NESTED, [("mode", "hot")])


class NativeClusterEdgeBehaviorTest(unittest.TestCase):
    """Pinna il comportamento NATIVO inteso sulla divergenza enum-casing che il
    cluster espone sui path favourites/recover/rule-default (stesso root dello slice 1).
    Native accetta un enum ri-castato (fix BABYCARE) e ne invia il grezzo; pyhОn+patch
    lo rifiuta. Divergenza VOLUTA, da rivalidare LIVE (vedi command_loader/rules)."""

    def test_cased_enum_value_accepted_by_native_rejected_by_pyhon(self) -> None:
        from custom_components.addhon.client.engine.parameter.enum import HonParameterEnum as NaEnum
        from custom_components.addhon._vendor.pyhon.parameter.enum import HonParameterEnum as PyEnum

        data = {"category": "command", "typology": "enum", "mandatory": 0,
                "defaultValue": "[dashboard]", "enumValues": ["dashboard"]}
        na = NaEnum("pf", dict(data), "ancillaryParameters")
        na.value = "DASHBOARD"  # casing tipico di un valore salvato in un favourite
        self.assertEqual(na.value, "dashboard")         # getter normalizza
        self.assertEqual(na.intern_value, "DASHBOARD")  # grezzo = ciò che si invierebbe
        # pyhОn+patch (oracolo di produzione) rifiuta il valore ri-castato: nel path
        # favourites/recover il ValueError sarebbe inghiottito dal suppress -> default.
        py = PyEnum("pf", dict(data), "ancillaryParameters")
        with self.assertRaises(ValueError):
            py.value = "DASHBOARD"


class ProtocolConformanceTest(unittest.TestCase):
    """Parte D: gli oggetti nativi soddisfano i Protocol del seam."""

    def test_native_objects_satisfy_protocols(self) -> None:
        na = pyhon_adapter._native_engine_appliance_cls()(FakeApi(), dict(_INFO), zone=0)
        _run(na.load_commands())
        self.assertIsInstance(na, interfaces.Appliance)
        for command in na.commands.values():
            self.assertIsInstance(command, interfaces.Command)
            for param in command.parameters.values():
                self.assertIsInstance(param, interfaces.Parameter)


if __name__ == "__main__":
    unittest.main()
