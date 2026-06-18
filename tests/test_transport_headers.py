"""Differential test del 4° pezzo del transport: build_auth_headers.

Oracolo = costruzione header di pyhОn: `ConnectionHandler._HEADERS | headers`
(handler/base.py:18-21 + handler/hon.py:66-68), dove `headers` = extra del
chiamante + i due token. `_HEADERS` usa `const.USER_AGENT`: lo carichiamo dal
vero const.py (puro, importabile a sé) così il test pinna anche il drift del UA.
handler/base.py importa aiohttp → non importabile a sé, quindi `_HEADERS` (2 chiavi)
è trascritto verbatim.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_OUR_HEADERS = _ROOT / "custom_components" / "addhon" / "client" / "transport" / "headers.py"
_PYHON_CONST = _ROOT / "custom_components" / "addhon" / "_vendor" / "pyhon" / "const.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _pyhon_headers(user_agent, cognito_token, id_token, extra=None):
    """Verbatim: pyhon _HEADERS | (extra + token)."""
    base = {"user-agent": user_agent, "Content-Type": "application/json"}
    headers = dict(extra) if extra else {}
    headers["cognito-token"] = cognito_token
    headers["id-token"] = id_token
    return base | headers


class BuildAuthHeadersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.build = _load(_OUR_HEADERS, "addhon_transport_headers").build_auth_headers
        self.ua = _load(_PYHON_CONST, "pyhon_const_for_headers").USER_AGENT

    def test_matches_pyhon(self) -> None:
        cases = [
            ("COG", "IDT", None),
            ("", "", None),
            ("c", "i", {}),
            ("c", "i", {"x-extra": "1"}),
            ("c", "i", {"user-agent": "OVERRIDE/1.0"}),          # extra sovrascrive base UA
            ("c", "i", {"cognito-token": "WILL_BE_REPLACED"}),    # token reale vince sull'extra
            ("c", "i", {"Content-Type": "text/plain", "id-token": "X"}),
        ]
        for cog, idt, extra in cases:
            with self.subTest(extra=extra):
                self.assertEqual(
                    self.build(cog, idt, extra),
                    _pyhon_headers(self.ua, cog, idt, extra),
                )

    def test_pinned(self) -> None:
        self.assertEqual(
            self.build("C", "I"),
            {
                "user-agent": "Chrome/999.999.999.999",
                "Content-Type": "application/json",
                "cognito-token": "C",
                "id-token": "I",
            },
        )

    def test_ua_matches_vendored_const(self) -> None:
        # Pin contro drift: il nostro USER_AGENT deve eguagliare quello di pyhОn.
        our_ua = _load(_OUR_HEADERS, "addhon_transport_headers2").USER_AGENT
        self.assertEqual(our_ua, self.ua)

    def test_tokens_always_present_and_win(self) -> None:
        h = self.build("REAL_COG", "REAL_ID", {"cognito-token": "fake", "id-token": "fake"})
        self.assertEqual(h["cognito-token"], "REAL_COG")
        self.assertEqual(h["id-token"], "REAL_ID")


if __name__ == "__main__":
    unittest.main()
