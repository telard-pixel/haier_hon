"""Parsing of the OAuth tokens from the hOn login redirect (addhOn transport).

Rewrite of `pyhon auth._parse_token_data`: from the redirect
`.../mobilesdk/detect/oauth/done#access_token=...&refresh_token=...&id_token=...`
it extracts the three tokens via the regex `name=(.*?)&` (up to the first `&`).

EXACT PRESERVATION (not hardening, unlike the appliance-list parser):
the tokens go to the cloud byte-identical and the auth flow is not offline-validatable,
so we replicate pyhOn's quirks to the letter:
- only `refresh_token` is URL-decoded (`unquote`); access/id stay raw;
- a token at the end WITHOUT a trailing `&` is NOT captured (the regex requires the `&`);
- `complete` = all three patterns HAVE matched (even if the captured value
  is empty, like pyhOn's `bool(findall and ...)`), not "all values non-empty".
Rewrote the STRUCTURE (data-driven helper + immutable dataclass), preserved the
BEHAVIOR (verified by the differential test against pyhOn).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote


@dataclass(frozen=True)
class OAuthTokens:
    """Tokens extracted from the OAuth redirect. `complete` = all three present.

    NB: `cognito_token` is NOT here: it comes from a separate POST (token-refresh),
    not from the redirect.
    """

    access_token: str = ""
    refresh_token: str = ""
    id_token: str = ""
    complete: bool = False


def parse_token_fragment(text: str) -> OAuthTokens:
    """Extract access/refresh/id token from the OAuth redirect text."""

    def _match(name: str) -> str | None:
        found = re.findall(f"{name}=(.*?)&", text)
        return found[0] if found else None

    access = _match("access_token")
    refresh = _match("refresh_token")
    id_token = _match("id_token")
    return OAuthTokens(
        access_token=access or "",
        # Only the refresh is URL-decoded, like pyhOn.
        refresh_token=unquote(refresh) if refresh is not None else "",
        id_token=id_token or "",
        # Like pyhOn: what counts is that the pattern MATCHED (not that the value is
        # non-empty), hence `None not in (...)`.
        complete=None not in (access, refresh, id_token),
    )
