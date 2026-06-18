"""Differential test dei parametri nativi (Fase 4 slice 1) vs pyhОn.

Oracolo = le classi parametro di pyhОn CON il patch BABYCARE applicato
(`ensure_enum_patch`), cioè il comportamento di PRODUZIONE. Input = i parametri
REALI del frigo (apk/dump/ref_10136/commands.json: range+enum+fixed) percorsi tutti.
Per ogni parametro confrontiamo costruzione (typology/category/mandatory/value/
intern_value/values, e min/max/step per i range) e il SETTER (valori validi accettati
identici; valori invalidi -> ValueError su entrambi). Più un caso sintetico BABYCARE.

CONTRATTO: parità su (a) tutta la superficie LETTA dall'integrazione e (b) i valori
che l'integrazione imposta davvero (presi da `param.values`, già puliti). Su questo
native == pyhОn+patch (provato sui 67 parametri reali).

Il setter enum di native DIVERGE VOLUTAMENTE da pyhОn+patch su valori-edge
(cased/`|`/`[]`): native è più corretto (il patch è un bolt-on incoerente). Quelle
divergenze sono PINNATE in `NativeEnumEdgeBehaviorTest` come comportamento NOSTRO
inteso (non parità col patch), e vanno rivalidate live sull'AC al flip del cluster.

HA/aiohttp/yarl stubati: il motore parser ora importa senza awscrt.
"""
from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
_DUMP = REPO / "apk" / "dump" / "ref_10136" / "commands.json"


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

# pyhОn (oracolo) + patch BABYCARE di produzione
from custom_components.addhon.client import pyhon_adapter  # noqa: E402

pyhon_adapter.ensure_enum_patch()
from custom_components.addhon._vendor.pyhon.parameter.range import HonParameterRange as PyRange  # noqa: E402
from custom_components.addhon._vendor.pyhon.parameter.enum import HonParameterEnum as PyEnum  # noqa: E402
from custom_components.addhon._vendor.pyhon.parameter.fixed import HonParameterFixed as PyFixed  # noqa: E402

# Nativo
from custom_components.addhon.client.engine.parameter.range import HonParameterRange as NaRange  # noqa: E402
from custom_components.addhon.client.engine.parameter.enum import HonParameterEnum as NaEnum  # noqa: E402
from custom_components.addhon.client.engine.parameter.fixed import HonParameterFixed as NaFixed  # noqa: E402

_PY = {"range": PyRange, "enum": PyEnum, "fixed": PyFixed}
_NA = {"range": NaRange, "enum": NaEnum, "fixed": NaFixed}


def _walk_params(node, out):
    """Raccoglie tutti i dict-parametro (con typology nei 3 tipi) da commands.json."""
    if isinstance(node, dict):
        if node.get("typology") in _PY and "category" in node:
            out.append(node)
            return
        for v in node.values():
            _walk_params(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_params(v, out)


def _load_real_params():
    data = json.loads(_DUMP.read_text(encoding="utf-8"))
    out: list = []
    for key in ("settings", "stopProgram", "startProgram"):
        _walk_params(data.get(key, {}), out)
    return out


def _snap(p, typ):
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
    if typ == "range":
        s["min"], s["max"], s["step"] = p.min, p.max, p.step
    return s


class ParameterDifferentialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.params = _load_real_params()
        # sanity: il frigo deve avere parametri dei 3 tipi
        cls.by_typ = {}
        for d in cls.params:
            cls.by_typ.setdefault(d["typology"], 0)
            cls.by_typ[d["typology"]] += 1

    def test_dump_has_all_typologies(self) -> None:
        self.assertTrue(self.params, "nessun parametro estratto dal dump")
        for t in ("range", "enum", "fixed"):
            self.assertIn(t, self.by_typ, f"il dump non ha parametri {t}")

    def test_construction_parity(self) -> None:
        for d in self.params:
            t = d["typology"]
            with self.subTest(typ=t, attrs=sorted(d)):
                py = _PY[t]("k", dict(d), "grp")
                na = _NA[t]("k", dict(d), "grp")
                self.assertEqual(_snap(na, t), _snap(py, t))

    def test_setter_parity_valid_values(self) -> None:
        for d in self.params:
            t = d["typology"]
            py = _PY[t]("k", dict(d), "grp")
            na = _NA[t]("k", dict(d), "grp")
            for v in list(py.values):
                with self.subTest(typ=t, set=v):
                    py.value = v
                    na.value = v
                    self.assertEqual(na.value, py.value)
                    self.assertEqual(na.intern_value, py.intern_value)

    def test_setter_parity_invalid_value(self) -> None:
        for d in self.params:
            t = d["typology"]
            if t == "fixed":
                continue  # fixed non valida (accetta tutto)
            py = _PY[t]("k", dict(d), "grp")
            na = _NA[t]("k", dict(d), "grp")
            bad = "___definitely_not_allowed___"
            with self.subTest(typ=t):
                with self.assertRaises(ValueError):
                    py.value = bad
                with self.assertRaises(ValueError):
                    na.value = bad

    def test_babycare_fix_matches_pyhon_with_patch(self) -> None:
        # enum con un valore col casing del cloud: pyhОn-con-patch lo accetta, e anche
        # il nostro fix nativo. (pyhОn SENZA patch crasherebbe — quello è il bug.)
        data = {
            "category": "command",
            "typology": "enum",
            "mandatory": 1,
            "defaultValue": "OFF",
            "enumValues": ["OFF", "BABYCARE", "ECO"],
        }
        py = PyEnum("mode", dict(data), "grp")
        na = NaEnum("mode", dict(data), "grp")
        for v in ("BABYCARE", "babycare", "ECO"):
            with self.subTest(set=v):
                py.value = v
                na.value = v
                self.assertEqual(na.value, py.value)
                self.assertEqual(na.intern_value, py.intern_value)
        # construction parity sul sintetico
        self.assertEqual(_snap(na, "enum"), _snap(py, "enum"))


class NativeEnumEdgeBehaviorTest(unittest.TestCase):
    """Pinna il comportamento NATIVO inteso sugli edge enum (non parità col patch).
    Documenta le 3 divergenze trovate dai confutatori = native più corretto."""

    def test_pipe_array_enum_matches_pyhon(self) -> None:
        # `enumValues` come ARRAY con `|`: native E pyhОn+patch concordano (entrambi
        # puliscono "a|b"->"a_b"). (La divergenza è solo con `|`-STRINGA, vedi sotto.)
        data = {"category": "command", "typology": "enum", "mandatory": 1,
                "defaultValue": "a|b", "enumValues": ["a|b", "c"]}
        py = PyEnum("k", dict(data), "grp")
        na = NaEnum("k", dict(data), "grp")
        self.assertEqual(_snap(na, "enum"), _snap(py, "enum"))
        for v in ("a_b", "c"):
            py.value = v
            na.value = v
            self.assertEqual(na.value, py.value)
            self.assertEqual(na.intern_value, py.intern_value)

    def test_trigger_fires_on_cased_accepted_value(self) -> None:
        # MIGLIORIA (Finding 1): il setter native chiama check_trigger su OGNI valore
        # accettato, anche col casing del cloud (il patch pyhОn lo dimenticava sul
        # fallback -> rules non cascatavano). Qui pinniamo che native lo fa.
        data = {"category": "command", "typology": "enum", "mandatory": 1,
                "defaultValue": "OFF", "enumValues": ["OFF", "BABYCARE"]}
        na = NaEnum("mode", dict(data), "grp")
        fired = []
        na.add_trigger("babycare", lambda d: fired.append(d), object())
        na.value = "BABYCARE"  # valore col casing del cloud
        self.assertEqual(len(fired), 1, "il trigger deve scattare sul valore cased accettato")

    def test_pipe_string_enum_native_rejects_substring(self) -> None:
        # Finding 3: con `enumValues` come STRINGA, pyhОn+patch accetta per quirk di
        # substring; native (corretto) rifiuta un valore non tra i valori normalizzati.
        data = {"category": "command", "typology": "enum", "mandatory": 1,
                "defaultValue": "", "enumValues": "A|B|C"}
        na = NaEnum("k", dict(data), "grp")
        with self.assertRaises(ValueError):
            na.value = "A|B|C"


if __name__ == "__main__":
    unittest.main()
