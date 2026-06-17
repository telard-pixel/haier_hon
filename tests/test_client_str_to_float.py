"""Loop di migrazione, primo esercizio: port di str_to_float in client/helpers.py.

DIFFERENTIAL TEST: carica in isolamento (importlib, niente package __init__, niente
aiohttp) SIA la str_to_float di pyhОn (_vendor/pyhon/helper.py = l'ORACOLO) SIA la
nostra (client/helpers.py), e verifica che diano lo STESSO risultato — o sollevino
la STESSA eccezione — su un set rappresentativo di input. Più alcuni valori
"pinned" che fissano il comportamento atteso (caratterizzazione).

Così la nostra implementazione è ancorata al comportamento reale di pyhОn: quando
un domani il parser passerà a usare la nostra, non cambia nulla.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PYHON_HELPER = _ROOT / "custom_components" / "addhon" / "_vendor" / "pyhon" / "helper.py"
_OUR_HELPER = _ROOT / "custom_components" / "addhon" / "client" / "helpers.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Input rappresentativi: stringhe intere/decimali, virgola, float, negativi,
# zero, spazi, e casi che devono sollevare (non numerici / None).
_INPUTS = [
    "5", "0", "-16", "42",
    "5.5", "5,5", "-16.5", "0.0", "3.14",
    5, 0, -16, 5.5, -16.5, 0.0,
    "  3 ",
    "abc", "", None, "1.2.3",
]


def _result_or_exc(fn, value):
    """(('ok', risultato)) oppure (('exc', tipo-eccezione))."""
    try:
        return ("ok", fn(value))
    except Exception as err:  # noqa: BLE001 - vogliamo confrontare il TIPO
        return ("exc", type(err).__name__)


class StrToFloatDifferentialTest(unittest.TestCase):
    def setUp(self) -> None:
        self.oracle = _load(_PYHON_HELPER, "pyhon_helper_oracle").str_to_float
        self.ours = _load(_OUR_HELPER, "addhon_client_helpers").str_to_float

    def test_matches_pyhon_on_all_inputs(self) -> None:
        for value in _INPUTS:
            with self.subTest(value=value):
                self.assertEqual(_result_or_exc(self.ours, value), _result_or_exc(self.oracle, value))

    def test_pinned_characterization(self) -> None:
        # Valori fissati (documentano il comportamento, incluso il quirk del troncamento).
        self.assertEqual(self.ours("5"), 5)
        self.assertEqual(self.ours("5.5"), 5.5)
        self.assertEqual(self.ours("5,5"), 5.5)      # virgola decimale
        self.assertEqual(self.ours("-16.5"), -16.5)
        self.assertEqual(self.ours(5.5), 5)          # QUIRK: float troncato da int()
        self.assertEqual(self.ours("  3 "), 3)       # int() tollera gli spazi
        with self.assertRaises(ValueError):
            self.ours("abc")
        with self.assertRaises(TypeError):
            self.ours(None)


if __name__ == "__main__":
    unittest.main()
