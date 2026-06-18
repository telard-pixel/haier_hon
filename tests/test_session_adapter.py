"""Guard del distacco TOTALE da pyhОn (Fase 4 completata).

Storia: la sessione hОn passava per l'adattatore-ponte `pyhon_adapter` (l'unico file
che importava `_vendor.pyhon`). Con `_vendor/` CANCELLATO, questa guardia verifica la
meta finale: NESSUN file dell'integrazione importa più `_vendor`, e `_vendor/` non
esiste. `pyhon_adapter` resta la factory del client nativo.
"""
from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_COMPONENT = _ROOT / "custom_components" / "addhon"
_ADAPTER = _COMPONENT / "client" / "pyhon_adapter.py"
_HON_CLIENT = _COMPONENT / "hon_client.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _vendor_imports(path: Path) -> list[str]:
    out: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = ("." * (node.level or 0)) + (node.module or "")
            if "_vendor" in mod:
                out.append(f"{path.name}: {mod}")
        elif isinstance(node, ast.Import):
            out.extend(f"{path.name}: {a.name}" for a in node.names if "_vendor" in a.name)
    return out


class TotalDetachGuardTest(unittest.TestCase):
    def test_vendor_dir_deleted(self) -> None:
        self.assertFalse((_COMPONENT / "_vendor").exists(), "_vendor/ esiste ancora")

    def test_no_vendor_imports_anywhere(self) -> None:
        offenders: list[str] = []
        for py in _COMPONENT.rglob("*.py"):
            offenders.extend(_vendor_imports(py))
        self.assertEqual(offenders, [], f"import _vendor residui: {offenders}")

    def test_adapter_loads_and_exposes_factories(self) -> None:
        adapter = _load(_ADAPTER, "addhon_pyhon_adapter")
        self.assertTrue(callable(adapter.create_session))
        self.assertTrue(callable(adapter.create_appliance))
        # la vecchia patch BABYCARE è stata rimossa (fix nativo nell'enum)
        self.assertFalse(hasattr(adapter, "ensure_enum_patch"))

    def test_hon_client_uses_native_factory(self) -> None:
        src = _HON_CLIENT.read_text(encoding="utf-8")
        self.assertIn("from .client.pyhon_adapter import create_session", src)
        self.assertIn("create_session(self._email, self._password)", src)
        self.assertNotIn("ensure_enum_patch", src)


if __name__ == "__main__":
    unittest.main()
