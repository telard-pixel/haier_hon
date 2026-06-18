"""Factory della sessione/appliance hОn native.

Storicamente era l'adattatore-ponte verso il pyhОn vendorizzato (l'unico file che
importava `_vendor.pyhon`). Con la Fase 4 completata (`_vendor/` CANCELLATO) qui non
c'è più alcun import di pyhОn: restano solo i due factory che costruiscono il client
NOSTRO. Tenerli dietro queste funzioni mantiene `hon_client.py` disaccoppiato dai
dettagli del client.

`create_session` ritorna un oggetto conforme a `interfaces.HonSession` (il nostro
`client.session.NativeHon`); `create_appliance` la `interfaces.Appliance`
(`client.engine.appliance.HonAppliance`). Il fix del bug BABYCARE è nativo nella
classe enum (`client.engine.parameter.enum`): la vecchia `ensure_enum_patch` che
rattoppava l'enum di pyhОn è stata RIMOSSA con `_vendor/`.
"""
from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Cache della classe ROOT appliance nativa (import lazy: l'engine importa senza awscrt).
_NATIVE_APPLIANCE_CLS: Any = None


def create_session(email: str, password: str) -> Any:
    """Crea la sessione hОn NATIVA (`client.session.NativeHon`).

    FLIP COMPLETO del transport (Fase 3 piece 4): auth, connessione, api, MQTT e
    orchestrazione sono NOSTRI; di pyhОn resta solo il motore parser
    (HonAppliance/HonCommandLoader, riusato dentro NativeHon). Prima qui si creava un
    `pyhon.Hon` col nostro auth INIETTATO (`install_native_auth`, ora superato): il
    transport pyhОn non gira più in produzione. Il chiamante la usa identica a prima
    (`__aenter__()` → `.appliances`).

    Import lazy di `NativeHon`: evita il ciclo (session.py importa questo modulo) e
    tiene `pyhon_adapter` importabile a secco (gli import di _vendor restano lazy,
    nei factory `create_appliance`/`ensure_enum_patch`).
    """
    from .session import NativeHon

    return NativeHon(email=email, password=password)


def _native_engine_appliance_cls() -> Any:
    """Ritorna la classe ROOT appliance NATIVA (`engine.appliance.HonAppliance`).

    Fase 4 slice 5: il ROOT è ora interamente nostro (prima era una sottoclasse del ROOT
    pyhОn col motore iniettato; ora è una classe standalone che usa attributi/loader/
    commands/rules/program/per-tipo TUTTI nativi). `_vendor` non è più coinvolto. Lazy
    (l'engine importa senza awscrt), cachata per processo.
    """
    global _NATIVE_APPLIANCE_CLS
    if _NATIVE_APPLIANCE_CLS is None:
        from .engine.appliance import HonAppliance as _NativeRoot

        _NATIVE_APPLIANCE_CLS = _NativeRoot
    return _NATIVE_APPLIANCE_CLS


def create_appliance(api: Any, appliance_data: dict, zone: int = 0) -> Any:
    """Costruisce l'appliance ROOT NATIVA (Fase 4 slice 5 — distacco TOTALE da pyhОn).

    Tutto il motore (loader/commands/rules/program/parametri/attributi/per-tipo + ROOT)
    è nostro: `_vendor` non viene più importato. L'oggetto ritornato è conforme al
    Protocol `interfaces.Appliance` (duck-typing). Import lazy.
    """
    return _native_engine_appliance_cls()(api, appliance_data, zone=zone)
