"""Test offline del flusso auth nativo (HonAuth) con sessione MOCKATA.

L'happy path è già LIVE-validato (apk/validate_auth_live.py: login reale → token
→ 4 appliance == pyhОn). Questo è il guard CI per la LOGICA del flusso (ordine
degli step, header, payload, parsing, rami): yarl stubato, nessuna rete, risposte
HTTP scriptate in ordine di chiamata.
"""
from __future__ import annotations

import asyncio
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
    # Stub HA minimi per far importare il package __init__.
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
    # Stub yarl.URL (auth.py fa URL(login_url, encoded=True)).
    yarl = _mod("yarl")
    if not hasattr(yarl, "URL"):
        class URL:
            def __init__(self, s, encoded=False):
                self._s = s

            def __str__(self):
                return self._s
        yarl.URL = URL


_install_stubs()

from custom_components.addhon.client.transport.auth import HonAuth, NativeAuthError  # noqa: E402
from custom_components.addhon.client.transport.device import HonDevice  # noqa: E402

AUTH = "https://account2.hon-smarthome.com"


class FakeResp:
    def __init__(self, status=200, text="", json=None, headers=None) -> None:
        self.status = status
        self._text = text
        self._json = json
        self.headers = headers or {}

    async def text(self):
        return self._text

    async def json(self, content_type=None):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Ritorna le risposte scriptate IN ORDINE di chiamata (il flusso è lineare)."""

    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.calls: list = []
        self.cookie_jar = types.SimpleNamespace(clear_domain=lambda d: None)

    def _next(self, method, url):
        self.calls.append((method, str(url)))
        if not self._responses:
            raise AssertionError(f"chiamata non prevista: {method} {url}")
        return self._responses.pop(0)

    def get(self, url, **kw):
        return self._next("GET", url)

    def post(self, url, **kw):
        return self._next("POST", url)


def _happy_responses():
    return [
        # _introduce: pagina authorize con url di login
        FakeResp(text="x url = '/s/login/p?startURL=%2Fhome' y"),
        # _handle_redirects: 2 redirect (Location)
        FakeResp(status=302, headers={"Location": f"{AUTH}/r1"}),
        FakeResp(status=302, headers={"Location": f"{AUTH}/r2?startURL=%2Fhome"}),
        # _open_login_page: fwuid + loaded
        FakeResp(text='..."fwuid":"FW123","loaded":{"APPLICATION@x":"y"}...'),
        # _login: events url
        FakeResp(json={"events": [{"attributes": {"values": {"url": f"{AUTH}/tokpage"}}}]}),
        # _get_token: pagina con href (no ProgressiveLogin)
        FakeResp(text="href = '/finaltok'"),
        # _get_token: pagina token finale
        FakeResp(text="#access_token=AAA&refresh_token=r%2Fb&id_token=CCC&"),
        # _api_auth
        FakeResp(json={"cognitoUser": {"Token": "COG123"}}),
    ]


class NativeAuthFlowTest(unittest.TestCase):
    def _auth(self, responses):
        return HonAuth(FakeSession(responses), "user@x.it", "pw", HonDevice())

    def test_happy_path(self) -> None:
        auth = self._auth(_happy_responses())
        asyncio.run(auth.authenticate())
        self.assertEqual(auth.id_token, "CCC")
        self.assertEqual(auth.access_token, "AAA")
        self.assertEqual(auth.refresh_token, "r/b")  # solo refresh urldecodato
        self.assertEqual(auth.cognito_token, "COG123")

    def test_no_auth_needed(self) -> None:
        # La pagina authorize è già la redirect coi token: niente login, niente cognito.
        auth = self._auth([
            FakeResp(text="...oauth/done#access_token=AAA&refresh_token=BBB&id_token=CCC&..."),
        ])
        asyncio.run(auth.authenticate())
        self.assertEqual(auth.id_token, "CCC")
        self.assertEqual(auth.cognito_token, "")  # _api_auth saltato (come pyhОn)

    def test_login_page_without_fwuid_raises(self) -> None:
        auth = self._auth([
            FakeResp(text="x url = '/s/login/p?startURL=%2Fhome' y"),
            FakeResp(status=302, headers={"Location": f"{AUTH}/r1"}),
            FakeResp(status=302, headers={"Location": f"{AUTH}/r2"}),
            FakeResp(text="pagina senza fwuid"),
        ])
        with self.assertRaises(NativeAuthError):
            asyncio.run(auth.authenticate())

    def test_api_auth_without_cognito_raises(self) -> None:
        responses = _happy_responses()
        responses[-1] = FakeResp(json={"cognitoUser": {}})  # niente Token
        auth = self._auth(responses)
        with self.assertRaises(NativeAuthError):
            asyncio.run(auth.authenticate())

    def test_step_order(self) -> None:
        # L'ordine delle chiamate riflette il flusso pyhОn.
        session = FakeSession(_happy_responses())
        auth = HonAuth(session, "u", "p", HonDevice())
        asyncio.run(auth.authenticate())
        methods = [m for m, _ in session.calls]
        self.assertEqual(methods, ["GET", "GET", "GET", "GET", "POST", "GET", "GET", "POST"])


if __name__ == "__main__":
    unittest.main()
