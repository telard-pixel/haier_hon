"""Factory for the native hOn session/appliance.

Historically this was the bridge adapter towards the vendored pyhOn (the only file
that imported `_vendor.pyhon`). With Phase 4 completed (`_vendor/` DELETED) there is
no longer any pyhOn import here: only the two factories that build OUR client remain.
Keeping them behind these functions keeps `hon_client.py` decoupled from the client
details.

`create_session` returns an object conforming to `interfaces.HonSession` (our
`client.session.NativeHon`); `create_appliance` the `interfaces.Appliance`
(`client.engine.appliance.HonAppliance`). The BABYCARE bug fix is native in the
enum class (`client.engine.parameter.enum`): the old `ensure_enum_patch` that
patched the pyhOn enum has been REMOVED along with `_vendor/`.
"""
from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Cache of the native ROOT appliance class (lazy import: the engine imports without awscrt).
_NATIVE_APPLIANCE_CLS: Any = None


def create_session(email: str, password: str) -> Any:
    """Create the NATIVE hOn session (`client.session.NativeHon`).

    Auth, connection, api, MQTT, orchestration and parser engine are all OURS
    (pyhOn deleted). The caller uses it as an async context manager
    (`__aenter__()` -> `.appliances`).

    Lazy import of `NativeHon`: avoids the cycle (session.py imports this module) and
    keeps `pyhon_adapter` importable dry (`NativeHon` pulls in awscrt via MQTT).
    """
    from .session import NativeHon

    return NativeHon(email=email, password=password)


def _native_engine_appliance_cls() -> Any:
    """Return the NATIVE ROOT appliance class (`engine.appliance.HonAppliance`).

    The ROOT is a standalone class that uses attributes/loader/commands/rules/program/
    per-type, ALL native. Lazy import (the engine imports without awscrt), cached per process.
    """
    global _NATIVE_APPLIANCE_CLS
    if _NATIVE_APPLIANCE_CLS is None:
        from .engine.appliance import HonAppliance as _NativeRoot

        _NATIVE_APPLIANCE_CLS = _NativeRoot
    return _NATIVE_APPLIANCE_CLS


def create_appliance(api: Any, appliance_data: dict, zone: int = 0) -> Any:
    """Build the NATIVE ROOT appliance (TOTAL detach from pyhOn).

    The whole engine (loader/commands/rules/program/parameters/attributes/per-type + ROOT)
    is ours: `_vendor` is no longer imported. The returned object conforms to the
    Protocol `interfaces.Appliance` (duck-typing). Lazy import.
    """
    return _native_engine_appliance_cls()(api, appliance_data, zone=zone)
