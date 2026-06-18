"""Offline guard del FLIP (pyhon_adapter.install_native_auth).

Validato LIVE (apk/validate_flip_live.py: la macchina pyhОn logga col NOSTRO auth
+ carica 4 appliance con comandi). Qui: guard CI che il monkeypatch colpisce il
bersaglio giusto (handler.hon.HonAuth -> nostro HonAuth) ed è idempotente. Stub
del modulo handler di pyhОn + yarl, così non serve aiohttp.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _mod(name: str) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        sys.modules[name] = m
    return m


def _install_stubs() -> None:
    # HA stubs (per il package __init__).
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
    # yarl stub (auth.py importa yarl.URL).
    yarl = _mod("yarl")
    if not hasattr(yarl, "URL"):
        yarl.URL = type("URL", (), {"__init__": lambda self, s, encoded=False: None})
    # Stub della catena handler di pyhОn (evita aiohttp): hon con un HonAuth sentinella.
    for name in (
        "custom_components.addhon._vendor",
        "custom_components.addhon._vendor.pyhon",
        "custom_components.addhon._vendor.pyhon.connection",
        "custom_components.addhon._vendor.pyhon.connection.handler",
    ):
        m = _mod(name)
        m.__path__ = []  # pacchetto fittizio
    hon_mod = _mod("custom_components.addhon._vendor.pyhon.connection.handler.hon")
    hon_mod.HonAuth = type("PyhonHonAuthSentinel", (), {})


_install_stubs()

from custom_components.addhon.client import pyhon_adapter  # noqa: E402
from custom_components.addhon.client.transport.auth import HonAuth as NativeHonAuth  # noqa: E402
from custom_components.addhon._vendor.pyhon.connection.handler import hon as _stub_hon  # noqa: E402


class NativeAuthFlipTest(unittest.TestCase):
    def setUp(self) -> None:
        pyhon_adapter._NATIVE_AUTH_INSTALLED = False
        _stub_hon.HonAuth = type("PyhonHonAuthSentinel", (), {})  # reset

    def tearDown(self) -> None:
        pyhon_adapter._NATIVE_AUTH_INSTALLED = False

    def test_install_patches_handler_to_native(self) -> None:
        self.assertIsNot(_stub_hon.HonAuth, NativeHonAuth)
        pyhon_adapter.install_native_auth()
        self.assertIs(_stub_hon.HonAuth, NativeHonAuth)
        self.assertTrue(pyhon_adapter._NATIVE_AUTH_INSTALLED)

    def test_idempotent(self) -> None:
        pyhon_adapter.install_native_auth()
        # Una seconda chiamata non ri-patcha (se qualcuno avesse rimesso il sentinel,
        # resterebbe): il flag protegge.
        sentinel = type("X", (), {})
        _stub_hon.HonAuth = sentinel
        pyhon_adapter.install_native_auth()
        self.assertIs(_stub_hon.HonAuth, sentinel)  # no-op alla seconda

    def test_native_auth_is_drop_in_interface(self) -> None:
        # Il nostro HonAuth deve esporre, SU UN'ISTANZA, l'interfaccia che l'handler
        # di pyhОn usa (i token sono attributi d'istanza, non di classe come le
        # @property di pyhОn — equivalente a runtime, confermato dalla live).
        inst = NativeHonAuth(None, "e@x", "p", None)  # __init__ non fa I/O
        for attr in (
            "authenticate", "refresh", "clear",
            "cognito_token", "id_token", "access_token", "refresh_token",
            "token_is_expired", "token_expires_soon",
        ):
            self.assertTrue(hasattr(inst, attr), f"manca {attr}")


if __name__ == "__main__":
    unittest.main()
