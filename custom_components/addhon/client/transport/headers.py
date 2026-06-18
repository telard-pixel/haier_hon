"""Header HTTP del transport addhОn.

Riscrittura della costruzione degli header autenticati di pyhОn
(`ConnectionHandler._HEADERS` in handler/base.py + il merge in
handler/hon.py:_check_headers): ogni richiesta autenticata porta user-agent +
Content-Type + i due token (cognito-token, id-token).

Funzione PURA: i token sono input, nessun segreto hardcoded. `USER_AGENT`
rispecchia oggi il valore di pyhОn (valore-dato, behavior-preserving, pinnato dal
differential test); il valore reale dell'app entrerà come passo separato.
"""
from __future__ import annotations

from typing import Mapping

# Valore-dato che rispecchia pyhon const.USER_AGENT (placeholder d'impersonazione).
USER_AGENT = "Chrome/999.999.999.999"
CONTENT_TYPE = "application/json"

# Header di base presenti su OGNI richiesta (= ConnectionHandler._HEADERS).
BASE_HEADERS: dict[str, str] = {
    "user-agent": USER_AGENT,
    "Content-Type": CONTENT_TYPE,
}


def build_auth_headers(
    cognito_token: str,
    id_token: str,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Header per una richiesta autenticata.

    Replica `self._HEADERS | headers` di pyhОn dove `headers` contiene gli
    `extra` del chiamante PIÙ i due token: gli `extra` (e i token) vincono sui
    base, i token sono sempre presenti.
    """
    overrides: dict[str, str] = dict(extra) if extra else {}
    overrides["cognito-token"] = cognito_token
    overrides["id-token"] = id_token
    return BASE_HEADERS | overrides
