"""HTTP headers of the addhOn transport.

Rewrite of pyhOn's authenticated header construction
(`ConnectionHandler._HEADERS` in handler/base.py + the merge in
handler/hon.py:_check_headers): every authenticated request carries user-agent +
Content-Type + the two tokens (cognito-token, id-token).

PURE function: the tokens are inputs, no hardcoded secret. `USER_AGENT`
today mirrors pyhOn's value (data value, behavior-preserving, pinned by the
differential test); the real app value will enter as a separate step.
"""
from __future__ import annotations

from typing import Mapping

# Data value that mirrors pyhon const.USER_AGENT (impersonation placeholder).
USER_AGENT = "Chrome/999.999.999.999"
CONTENT_TYPE = "application/json"

# Base headers present on EVERY request (= ConnectionHandler._HEADERS).
BASE_HEADERS: dict[str, str] = {
    "user-agent": USER_AGENT,
    "Content-Type": CONTENT_TYPE,
}


def build_auth_headers(
    cognito_token: str,
    id_token: str,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Headers for an authenticated request.

    Replicates pyhOn's `self._HEADERS | headers` where `headers` contains the
    caller's `extra` PLUS the two tokens: the `extra` (and the tokens) win over the
    base ones, the tokens are always present.
    """
    overrides: dict[str, str] = dict(extra) if extra else {}
    overrides["cognito-token"] = cognito_token
    overrides["id-token"] = id_token
    return BASE_HEADERS | overrides
