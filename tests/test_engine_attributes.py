"""Differential test dell'attributo nativo (Fase 4 slice 2) vs pyhОn.

Oracolo = `_vendor/pyhon/attributes.HonAttribute`. Input = i dati REALI dello
shadow del frigo (apk/dump/ref_10136/attributes.json -> shadow.parameters), più
casi sintetici per update/lock. Confrontiamo l'intera superficie osservabile:
costruzione (`value`/`last_update`/`str`), gli update (str e dict, con/ senza
shield) e il comportamento di `lock` (True entro la finestra, False dopo).

UNICA divergenza voluta vs pyhОn = il fix di deprecazione: native usa
`datetime.now(timezone.utc)` (aware) dove pyhОn usa `datetime.utcnow()` (naive).
È un dettaglio INTERNO: il `lock` è scritto e letto solo dentro la classe, quindi
il comportamento osservabile è identico (lo verifichiamo costruendo per ciascuna
classe un lock-timestamp "fresco" e uno "scaduto" con la sua convenzione di clock).
La scelta aware è pinnata in `NativeAttributeBehaviorTest`.

HA/aiohttp/yarl stubati: l'import del package addhon tira dentro homeassistant.
"""
from __future__ import annotations

import json
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
_DUMP = REPO / "apk" / "dump" / "ref_10136" / "attributes.json"


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

from custom_components.addhon._vendor.pyhon.attributes import HonAttribute as PyAttr  # noqa: E402
from custom_components.addhon.client.engine.attributes import HonAttribute as NaAttr  # noqa: E402


def _real_shadow_params() -> dict:
    data = json.loads(_DUMP.read_text(encoding="utf-8"))
    return data.get("shadow", {}).get("parameters", {})


def _snap(a) -> dict:
    # include `lock` così OGNI caso di parità rileva una divergenza del lock, non
    # solo i test dedicati (gap segnalato dall'audit dei confutatori).
    return {"value": a.value, "str": str(a), "last_update": a.last_update, "lock": a.lock}


class AttributeDifferentialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.params = _real_shadow_params()

    def test_dump_has_params(self) -> None:
        self.assertTrue(self.params, "nessun parametro shadow estratto dal dump")

    def test_construction_parity(self) -> None:
        for name, data in self.params.items():
            with self.subTest(name=name):
                py = PyAttr(dict(data))
                na = NaAttr(dict(data))
                self.assertEqual(_snap(na), _snap(py))
                # tipo del value identico (es. "00"->0 int, non "00")
                self.assertEqual(type(na.value), type(py.value))

    def test_str_update_parity(self) -> None:
        for name, data in self.params.items():
            with self.subTest(name=name):
                py = PyAttr(dict(data))
                na = NaAttr(dict(data))
                self.assertEqual(py.update("42"), na.update("42"))
                self.assertEqual(_snap(na), _snap(py))

    def test_dict_update_parity(self) -> None:
        new = {"parNewVal": "7", "lastUpdate": "2024-05-01T12:00:00"}
        for name, data in self.params.items():
            with self.subTest(name=name):
                py = PyAttr(dict(data))
                na = NaAttr(dict(data))
                self.assertEqual(py.update(dict(new)), na.update(dict(new)))
                self.assertEqual(_snap(na), _snap(py))

    def test_invalid_last_update_parity(self) -> None:
        bad = {"parNewVal": "1", "lastUpdate": "not-a-date"}
        py = PyAttr(dict(bad))
        na = NaAttr(dict(bad))
        self.assertIsNone(py.last_update)
        self.assertIsNone(na.last_update)
        self.assertEqual(_snap(na), _snap(py))

    def test_invalid_last_update_after_valid_parity(self) -> None:
        # un lastUpdate valido, poi uno spazzatura: deve RESETTARE last_update a None
        # su entrambe (copre il ramo except che azzera, non solo il caso da-init).
        valid = {"parNewVal": "1", "lastUpdate": "2024-01-01T00:00:00"}
        py = PyAttr(dict(valid))
        na = NaAttr(dict(valid))
        self.assertIsNotNone(py.last_update)
        self.assertIsNotNone(na.last_update)
        py.update({"parNewVal": "2", "lastUpdate": "garbage"})
        na.update({"parNewVal": "2", "lastUpdate": "garbage"})
        self.assertIsNone(py.last_update)
        self.assertIsNone(na.last_update)
        self.assertEqual(_snap(na), _snap(py))

    def test_synthetic_value_parity(self) -> None:
        # Il corpus reale del frigo è tutto stringhe-intere: questo lascia DARK il
        # fallback `except ValueError` del getter value (linee 41-42) e il ramo
        # float/virgola di str_to_float. Qui li copriamo con valori non-int,
        # confrontando value + str + tipo del value (kill mutanti M9/M10/float).
        for v in ["5.5", "5,5", "-3,25", "12.0", "abc", "00", "-16", " 5 ", ""]:
            with self.subTest(parNewVal=v):
                py = PyAttr({"parNewVal": v})
                na = NaAttr({"parNewVal": v})
                self.assertEqual(_snap(na), _snap(py))
                self.assertEqual(type(na.value), type(py.value))

    def test_missing_parnewval_parity(self) -> None:
        # parNewVal assente (dict parziale, o vuoto): value deve cadere a "" su
        # entrambe (kill mutante M11b che usava "0" di default).
        for data in ({"lastUpdate": "2024-01-01T00:00:00"}, {}):
            with self.subTest(data=data):
                py = PyAttr(dict(data))
                na = NaAttr(dict(data))
                self.assertEqual(_snap(na), _snap(py))

    def test_missing_parnewval_on_update_resets_value_parity(self) -> None:
        # parNewVal assente su un UPDATE di un valore già presente: deve RESETTARE a
        # "" (non tenere il vecchio). Il caso da-init non lo distingue (parte da "");
        # serve un update su valore non vuoto (kill mutante M5/M11a keep-old).
        seed = {"parNewVal": "5", "lastUpdate": "2024-01-01T00:00:00"}
        py = PyAttr(dict(seed))
        na = NaAttr(dict(seed))
        py.update({"lastUpdate": "2024-02-02T00:00:00"})  # niente parNewVal
        na.update({"lastUpdate": "2024-02-02T00:00:00"})
        self.assertEqual(_snap(na), _snap(py))
        self.assertEqual(na._value, "")  # conferma il reset, non il keep-old

    def test_nonstring_parnewval_parity(self) -> None:
        # parNewVal non-stringa può arrivare da un push MQTT (json.loads -> int/
        # float/bool). value deve combaciare (str_to_float gestisce int/float, col
        # quirk int(5.5)->5); il tipo del value deve coincidere.
        for v in (7, 5.5, True):
            with self.subTest(parNewVal=v):
                py = PyAttr({"parNewVal": v})
                na = NaAttr({"parNewVal": v})
                self.assertEqual(na.value, py.value)
                self.assertEqual(type(na.value), type(py.value))
        # parNewVal=None: il getter value solleva (int(None)->TypeError, non
        # mascherato) su entrambe in modo identico.
        py_n = PyAttr({"parNewVal": None})
        na_n = NaAttr({"parNewVal": None})
        with self.assertRaises(TypeError):
            _ = py_n.value
        with self.assertRaises(TypeError):
            _ = na_n.value

    def test_fresh_lock_blocks_nonshield_update_parity(self) -> None:
        shield = {"parNewVal": "5", "lastUpdate": "2024-01-01T00:00:00"}
        later = {"parNewVal": "999"}
        py = PyAttr({"parNewVal": "0"})
        na = NaAttr({"parNewVal": "0"})
        # shield update -> entrambe lockate, valore applicato
        self.assertEqual(py.update(dict(shield), shield=True), na.update(dict(shield), shield=True))
        self.assertTrue(py.lock)
        self.assertTrue(na.lock)
        # update non-shield mentre lockate: rifiutato su entrambe, valore invariato
        self.assertEqual(py.update(dict(later)), na.update(dict(later)))
        self.assertFalse(py.update(dict(later)))
        self.assertEqual(_snap(na), _snap(py))
        # un altro shield update passa su entrambe
        self.assertEqual(py.update(dict(later), shield=True), na.update(dict(later), shield=True))
        self.assertEqual(_snap(na), _snap(py))

    def test_no_lock_by_default_parity(self) -> None:
        py = PyAttr({"parNewVal": "0"})
        na = NaAttr({"parNewVal": "0"})
        self.assertFalse(py.lock)
        self.assertFalse(na.lock)

    def test_stale_lock_expires_parity(self) -> None:
        # lock-timestamp scaduto (> _LOCK_TIMEOUT fa): entrambe devono tornare
        # sbloccate. Ogni classe usa la SUA convenzione di clock (py=naive utc,
        # na=aware utc) ma il booleano osservabile deve coincidere.
        py = PyAttr({"parNewVal": "0"})
        na = NaAttr({"parNewVal": "0"})
        py._lock_timestamp = datetime.utcnow() - timedelta(seconds=20)
        na._lock_timestamp = datetime.now(timezone.utc) - timedelta(seconds=20)
        self.assertFalse(py.lock)
        self.assertFalse(na.lock)
        # ora un update non-shield passa su entrambe
        self.assertEqual(py.update({"parNewVal": "3"}), na.update({"parNewVal": "3"}))
        self.assertEqual(_snap(na), _snap(py))


class NativeAttributeBehaviorTest(unittest.TestCase):
    """Pinna il comportamento NATIVO inteso (divergenza voluta vs pyhОn)."""

    def test_lock_timestamp_is_timezone_aware(self) -> None:
        # FIX deprecazione: native usa datetime.now(timezone.utc) (aware), non il
        # deprecato utcnow() (naive). Pinniamolo per evitare regressioni.
        na = NaAttr({"parNewVal": "0"})
        na.update({"parNewVal": "1"}, shield=True)
        self.assertIsNotNone(na._lock_timestamp)
        self.assertIsNotNone(na._lock_timestamp.tzinfo)
        self.assertEqual(na._lock_timestamp.utcoffset(), timedelta(0))
        # e lock funziona senza errori naive/aware
        self.assertTrue(na.lock)


if __name__ == "__main__":
    unittest.main()
