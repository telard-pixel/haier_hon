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
    """Sottoclasse dell'appliance ROOT di pyhОn col CLUSTER comandi NATIVO iniettato
    (Fase 4 slice 3). Definita lazy (sottoclassa una classe pyhОn importata lazy) e
    cachata per processo.

    PRONTA E DIFFERENTIAL-TESTATA, ma NON ancora usata in produzione: `create_appliance`
    ritorna ancora il ROOT pyhОn puro. Il FLIP è RIMANDATO allo slice 4 (vedi sotto).
    Oggi questa classe è esercitata solo dai test (tests/test_engine_cluster.py), che
    la diffano contro il ROOT pyhОn sui dati reali del frigo.

    Override (i punti del ROOT che toccano il tipo dei parametri):
    - `load_commands`: usa il `HonCommandLoader` NATIVO -> commands/rules/program/
      parametri tutti nostri. Stesso ordine di scrittura dello stato dell'appliance
      di pyhОn (commands -> additional_data -> appliance_model -> sync).
    - `sync_params_to_command`: l'`isinstance` di pyhОn era contro il SUO range; ora
      i parametri sono nativi (non sottoclassi di pyhОn) -> usiamo il range NOSTRO,
      altrimenti i range cadrebbero sul ramo stringa (regressione sul send-path).

    PERCHE' IL FLIP E' RIMANDATO (vincolo trovato dal pool confutatori, slice 3):
    le appliance per-tipo `_extra` (`_vendor/pyhon/appliances/base.py`, `td.py`, ...)
    fanno `isinstance(param, HonParameterProgram/HonParameterFixed)` di pyhОn a OGNI
    poll (es. base.py mappa `program.ids` -> `programName`; td.py sopprime `dryLevel`).
    Con i parametri nativi quegli isinstance fallirebbero -> regressione user-visible
    (`programName`="No Program" per gli apparecchi con programma attivo; `dryLevel` TD
    non soppresso). Quei siti isinstance NON erano negli "11" del ROOT: stanno nelle
    per-tipo = slice 4. Quindi cluster (slice 3) e per-tipo (slice 4) devono flippare
    INSIEME. `sync_parameter`/`sync_command` del ROOT restano invece MORTI (nessun
    chiamante) e si rimuovono col ROOT nativo (slice 5).
    """
    global _NATIVE_APPLIANCE_CLS
    if _NATIVE_APPLIANCE_CLS is not None:
        return _NATIVE_APPLIANCE_CLS

    from .._vendor.pyhon.appliance import HonAppliance
    from .engine.command_loader import HonCommandLoader
    from .engine.parameter.range import HonParameterRange

    class NativeEngineAppliance(HonAppliance):  # type: ignore[valid-type,misc]
        async def load_commands(self) -> None:
            command_loader = HonCommandLoader(self.api, self)
            await command_loader.load_commands()
            self._commands = command_loader.commands
            self._additional_data = command_loader.additional_data
            self._appliance_model = command_loader.appliance_data
            self.sync_params_to_command("settings")

        def sync_params_to_command(self, command_name: str) -> None:
            if not (command := self.commands.get(command_name)):
                return
            for key in command.setting_keys:
                if (
                    new := self.attributes.get("parameters", {}).get(key)
                ) is None or new.value == "":
                    continue
                setting = command.settings[key]
                try:
                    if not isinstance(setting, HonParameterRange):
                        command.settings[key].value = str(new.value)
                    else:
                        command.settings[key].value = float(new.value)
                except ValueError as error:
                    _LOGGER.info("Can't set %s - %s", key, error)
                    continue

    _NATIVE_APPLIANCE_CLS = NativeEngineAppliance
    return _NATIVE_APPLIANCE_CLS


def create_appliance(api: Any, appliance_data: dict, zone: int = 0) -> Any:
    """Costruisce un HonAppliance di pyhОn (il MOTORE parser che ancora riusiamo).

    NB FLIP RIMANDATO (Fase 4 slice 3): il cluster comandi NATIVO è scritto e
    differential-testato (`_native_engine_appliance_cls` + tests/test_engine_cluster.py),
    ma NON lo iniettiamo ancora in produzione: il pool confutatori ha mostrato che
    flippare i parametri a nativi ROMPE le appliance per-tipo `_extra` di pyhОn
    (`appliances/base.py`/`td.py`), che fanno `isinstance` contro le classi parametro
    di pyhОn a ogni poll. Cluster (slice 3) e per-tipo (slice 4) devono quindi flippare
    INSIEME -> finché slice 4 non è pronto, qui si ritorna il ROOT pyhОn puro.

    Tenere la costruzione qui mantiene `pyhon_adapter` l'UNICO file di `client/` che
    importa `_vendor.pyhon` (MIGRATION.md regola 1). L'oggetto ritornato è conforme al
    Protocol `interfaces.Appliance` (duck-typing). Import lazy.
    """
    from .._vendor.pyhon.appliance import HonAppliance

    return HonAppliance(api, appliance_data, zone=zone)


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
