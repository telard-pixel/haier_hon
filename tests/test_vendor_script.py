"""Guard del vendor script (scripts/vendor_pyhon.py).

Dopo la potatura del transport (Fase 3 piece 4b) il vendor script riscrive
`_vendor/pyhon/__init__.py` con `_ENGINE_ONLY_INIT`. Questo test blinda che quella
costante combaci BYTE-A-BYTE col file committato: altrimenti un rigenero
(`python scripts/vendor_pyhon.py`) modificherebbe il file (churn) e potenzialmente
reintrodurrebbe un mismatch. Importa solo stdlib (lo script è importabile a secco).
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "vendor_pyhon.py"
_VENDOR_INIT = _ROOT / "custom_components" / "addhon" / "_vendor" / "pyhon" / "__init__.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("addhon_vendor_pyhon", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VendorScriptTest(unittest.TestCase):
    def test_prune_init_matches_committed_file(self) -> None:
        script = _load_script()
        committed = _VENDOR_INIT.read_text(encoding="utf-8")
        self.assertEqual(
            script._ENGINE_ONLY_INIT,
            committed,
            "scripts/vendor_pyhon.py _ENGINE_ONLY_INIT diverge da _vendor/pyhon/__init__.py: "
            "un rigenero modificherebbe il file. Allineali.",
        )

    def test_committed_init_is_docstring_only(self) -> None:
        # Il transport è rimosso: l'__init__ non importa più Hon/HonAPI/connection.
        # L'invariante reale: è SOLO docstring, nessuna riga di import (la prosa cita
        # "connection" solo a parole, non come import).
        committed = _VENDOR_INIT.read_text(encoding="utf-8")
        import_lines = [
            ln for ln in committed.splitlines()
            if ln.strip().startswith(("import ", "from "))
        ]
        self.assertEqual(import_lines, [], f"__init__ non più solo-docstring: {import_lines}")
        self.assertNotIn("from .connection", committed)
        self.assertNotIn("from .hon import", committed)


if __name__ == "__main__":
    unittest.main()
