"""Adattatore-ponte verso il pyhОn vendorizzato (transizione).

Durante la migrazione questo è l'UNICO file di `client/` che importa
`_vendor.pyhon` (vedi MIGRATION.md, regola 1). Il corpo dell'integrazione
(`hon_client.py`) ottiene la sessione hОn DA QUI, non più con un import diretto
di `_vendor.pyhon`: così è disaccoppiato da pyhОn dietro questa funzione, e
quando arriverà il transport nativo si cambia solo qui.

`create_session` ritorna un oggetto conforme a `interfaces.HonSession`
(oggi: `pyhon.Hon`; domani: il client nativo). Qui vive anche la patch BABYCARE
di HonParameterEnum (anch'essa tocca `_vendor`, quindi sta nel ponte).
"""
from __future__ import annotations

import logging
import threading
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Stato della patch BABYCARE: globale di processo e thread-safe tra config entry
# (la classe HonParameterEnum di pyhОn è condivisa). Vive qui perché questo è
# l'unico file che importa _vendor.pyhon.parameter.enum.
# NB: con il CLUSTER nativo (Fase 4 slice 3) il motore non istanzia più l'enum di
# pyhОn (usa il nostro, che ha il fix BABYCARE alla radice): questa patch è ormai
# un no-op innocuo, si rimuove con la cancellazione di _vendor (slice 5).
_ENUM_PATCH_LOCK = threading.Lock()
_ENUM_PATCH_APPLIED = False

# Cache della sottoclasse appliance transitoria (Fase 4 slice 3). Costruita una
# sola volta perché sottoclassa una classe pyhОn importata lazy.
_NATIVE_APPLIANCE_CLS: Any = None

# NB: il vecchio `install_native_auth` (FLIP-by-injection nell'handler pyhОn) è stato
# RIMOSSO nel piece 4b: il transport pyhОn (connection/) non esiste più, la sessione
# nativa (NativeHon) usa il nostro auth direttamente. Non serve più iniettare nulla.


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


def ensure_enum_patch() -> None:
    """Applica una sola volta per processo la patch BABYCARE di HonParameterEnum.

    pyhOn crasha su load_commands() dell'asciugatrice TD perché il valore
    "BABYCARE" è nell'elenco dei valori ammessi ma il confronto stringa fallisce
    per un bug interno del setter HonParameterEnum.value. La patch accetta il
    valore se è già presente in _values.

    È best-effort e idempotente: protetta da un lock di modulo (la classe pyhOn è
    globale e condivisa tra tutte le config entry) e applicata al più una volta,
    catturando il setter ORIGINALE una sola volta per non annidare le closure a
    ogni reauth. In caso di errore il flag resta False, così un setup successivo
    può ritentare.
    """
    global _ENUM_PATCH_APPLIED
    with _ENUM_PATCH_LOCK:
        if _ENUM_PATCH_APPLIED:
            return
        try:
            from .._vendor.pyhon.parameter.enum import HonParameterEnum as _HonEnum

            _orig_setter = _HonEnum.value.fset

            def _patched_setter(instance, value):
                try:
                    _orig_setter(instance, value)
                except ValueError:
                    # Accetta il valore se è già presente nella lista (case-sensitive)
                    if value in instance._values:
                        instance._value = value
                        _LOGGER.debug("Patch enum BABYCARE applicata per valore: %s", value)
                    else:
                        raise

            _HonEnum.value = property(
                _HonEnum.value.fget, _patched_setter, _HonEnum.value.fdel
            )
            _ENUM_PATCH_APPLIED = True
            _LOGGER.debug("Patch HonParameterEnum applicata")
        except Exception as patch_err:
            # Best-effort: non impostiamo il flag così un setup successivo ritenta.
            _LOGGER.warning("Impossibile applicare la patch HonParameterEnum: %s", patch_err)
