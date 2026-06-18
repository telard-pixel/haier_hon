"""Golden test dei parametri nativi (Fase 4). Riusa i 67 parametri REALI del frigo
(apk/dump/ref_10136/commands.json: range+enum+fixed) e ne congela costruzione + setter.

Storia: era un differential test vs pyhОn+patch BABYCARE; con `_vendor/` cancellato è
diventato golden (l'output nativo era provato == pyhОn al checkpoint 5a). Il fix
BABYCARE è nativo nell'enum; le divergenze enum-edge restano pinnate sotto.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _golden import REPO, frozen, install_stubs  # noqa: E402

install_stubs()
_DUMP = REPO / "tests" / "fixtures" / "ref_10136" / "commands.json"

from custom_components.addhon.client.engine.parameter.range import HonParameterRange as NaRange  # noqa: E402
from custom_components.addhon.client.engine.parameter.enum import HonParameterEnum as NaEnum  # noqa: E402
from custom_components.addhon.client.engine.parameter.fixed import HonParameterFixed as NaFixed  # noqa: E402

_NA = {"range": NaRange, "enum": NaEnum, "fixed": NaFixed}


def _walk_params(node, out):
    if isinstance(node, dict):
        if node.get("typology") in _NA and "category" in node:
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
        "key": p.key, "category": p.category, "typology": p.typology,
        "mandatory": p.mandatory, "group": p.group, "value": p.value,
        "intern_value": p.intern_value, "values": list(p.values),
    }
    if typ == "range":
        s["min"], s["max"], s["step"] = p.min, p.max, p.step
    return s


def _native_snapshot():
    params = _load_real_params()
    out = {"by_typ": {}, "items": []}
    for d in params:
        t = d["typology"]
        out["by_typ"][t] = out["by_typ"].get(t, 0) + 1
        item = {"construct": _snap(_NA[t]("k", dict(d), "grp"), t)}
        # setter sui valori validi: (value, intern_value) risultanti
        na = _NA[t]("k", dict(d), "grp")
        setter = []
        for v in list(na.values):
            na.value = v
            setter.append([na.value, na.intern_value])
        item["setter_valid"] = setter
        # setter su valore invalido
        if t == "fixed":
            item["setter_invalid"] = "n/a"
        else:
            na2 = _NA[t]("k", dict(d), "grp")
            try:
                na2.value = "___definitely_not_allowed___"
                item["setter_invalid"] = "accepted"
            except ValueError:
                item["setter_invalid"] = "ValueError"
        if t == "range":
            # Probe NUMERICHE del range setter: fuori-range e off-step. Senza queste,
            # l'unico invalid è una stringa non-numerica che solleva già in str_to_float
            # (prima dei check min/max/step) -> regressioni del bound/step invisibili.
            probes: dict = {}
            nr = _NA[t]("k", dict(d), "grp")
            try:
                nr.value = nr.max + (nr.step or 1) * 1000
                probes["out_of_range"] = "accepted"
            except ValueError:
                probes["out_of_range"] = "ValueError"
            nr2 = _NA[t]("k", dict(d), "grp")
            try:
                nr2.value = str(nr2.min + 0.5)  # stringa: evita il troncamento int di str_to_float
                probes["off_step"] = "accepted"
            except ValueError:
                probes["off_step"] = "ValueError"
            item["range_probes"] = probes
        out["items"].append(item)
    return out


class ParameterGoldenTest(unittest.TestCase):
    def test_dump_has_all_typologies(self) -> None:
        snap = _native_snapshot()
        self.assertTrue(snap["items"])
        for t in ("range", "enum", "fixed"):
            self.assertIn(t, snap["by_typ"])

    def test_native_params_match_golden(self) -> None:
        snap = _native_snapshot()
        self.assertEqual(snap, frozen("engine_parameters", snap))


class NativeEnumEdgeBehaviorTest(unittest.TestCase):
    """Comportamento NATIVO inteso sugli edge enum (fix BABYCARE + divergenze pinnate)."""

    def test_babycare_cased_value_accepted(self) -> None:
        data = {"category": "command", "typology": "enum", "mandatory": 1,
                "defaultValue": "OFF", "enumValues": ["OFF", "BABYCARE", "ECO"]}
        na = NaEnum("mode", dict(data), "grp")
        # accetta sia il casing del cloud sia quello pulito; value normalizza, intern_value resta grezzo
        na.value = "BABYCARE"
        self.assertEqual(na.value, "babycare")
        self.assertEqual(na.intern_value, "BABYCARE")
        na.value = "eco"
        self.assertEqual(na.value, "eco")

    def test_trigger_fires_on_cased_accepted_value(self) -> None:
        data = {"category": "command", "typology": "enum", "mandatory": 1,
                "defaultValue": "OFF", "enumValues": ["OFF", "BABYCARE"]}
        na = NaEnum("mode", dict(data), "grp")
        fired = []
        na.add_trigger("babycare", lambda d: fired.append(d), object())
        na.value = "BABYCARE"
        self.assertEqual(len(fired), 1)

    def test_pipe_string_enum_native_rejects_substring(self) -> None:
        data = {"category": "command", "typology": "enum", "mandatory": 1,
                "defaultValue": "", "enumValues": "A|B|C"}
        na = NaEnum("k", dict(data), "grp")
        with self.assertRaises(ValueError):
            na.value = "A|B|C"


if __name__ == "__main__":
    unittest.main()
