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
_ENUM_PATCH_LOCK = threading.Lock()
_ENUM_PATCH_APPLIED = False

# FLIP dell'auth: stato del monkeypatch che fa usare alla macchina pyhОn il
# NOSTRO HonAuth nativo (drop-in). Idempotente, thread-safe.
_NATIVE_AUTH_LOCK = threading.Lock()
_NATIVE_AUTH_INSTALLED = False


def install_native_auth() -> None:
    """FLIP: sostituisce l'HonAuth di pyhОn col NOSTRO auth nativo.

    Il nostro `client.transport.auth.HonAuth` è un drop-in (stessa interfaccia:
    cognito_token/id_token/refresh_token/authenticate/refresh/clear/token_*). Lo
    iniettiamo nel namespace dell'handler di pyhОn (`HonConnectionHandler.create`
    fa `self._auth = HonAuth(...)` con lookup del nome a runtime), così il login
    di produzione gira sul NOSTRO flusso (validato live), tenendo api+parser di
    pyhОn. Stesso meccanismo della patch enum; idempotente e best-effort.
    """
    global _NATIVE_AUTH_INSTALLED
    with _NATIVE_AUTH_LOCK:
        if _NATIVE_AUTH_INSTALLED:
            return
        try:
            from .._vendor.pyhon.connection.handler import hon as _hon_handler
            from .transport.auth import HonAuth as _NativeHonAuth

            _hon_handler.HonAuth = _NativeHonAuth
            _NATIVE_AUTH_INSTALLED = True
            _LOGGER.info("addhОn: auth nativo iniettato in pyhОn (flip)")
        except Exception as err:  # pragma: no cover - difensivo
            _LOGGER.warning("addhОn: impossibile installare l'auth nativo: %s", err)


def create_session(email: str, password: str) -> Any:
    """Crea la sessione hОn autenticabile (context manager async).

    Il chiamante la usa via `__aenter__()` e ne legge `.appliances`, esattamente
    come prima. L'import di pyhОn è lazy (avviene solo qui, alla creazione) e
    riporta il messaggio amichevole se la libreria manca. Prima di creare la
    sessione installa il FLIP dell'auth (il login userà il nostro auth nativo).
    """
    install_native_auth()
    try:
        from .._vendor.pyhon import Hon
    except ImportError as err:  # pragma: no cover - solo se il vendor manca
        raise ImportError("La libreria pyhOn non è installata.") from err

    return Hon(email=email, password=password)


def create_appliance(api: Any, appliance_data: dict, zone: int = 0) -> Any:
    """Costruisce un HonAppliance di pyhОn (il MOTORE parser che ancora riusiamo).

    Il `Hon` nativo (`client/session.py`) orchestra il setup ma RIUSA questo
    motore, iniettandogli il NOSTRO `api` (transport.api.HonApi). Tenere la
    costruzione qui mantiene `pyhon_adapter` l'UNICO file di `client/` che importa
    `_vendor.pyhon` (MIGRATION.md regola 1). L'oggetto ritornato è conforme al
    Protocol `interfaces.Appliance` (duck-typing). Import lazy.
    """
    from .._vendor.pyhon.appliance import HonAppliance

    return HonAppliance(api, appliance_data, zone=zone)


async def create_mqtt(hon: Any, mobile_id: str) -> Any:
    """Avvia il MQTTClient di pyhОn (push background AWS IoT) per la sessione nativa.

    pyhОn lo crea in `Hon.setup()`; lo riusiamo finché non riscriviamo/decidiamo
    il transport MQTT (è in `_vendor/connection/`, bersaglio del piece 4). Import
    lazy: `mqtt.py` importa awscrt/awsiot, assenti negli ambienti di test offline.
    `MQTTClient` legge `hon.api`, `hon.appliances`, `hon.notify` dall'oggetto passato.
    """
    from .._vendor.pyhon.connection.mqtt import MQTTClient

    return await MQTTClient(hon, mobile_id).create()


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
