"""Client asincrono per le API hOn di Haier."""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

_LOGGER = logging.getLogger(__name__)

_SERIAL_ATTRS = ("serial_number", "serialNumber", "mac_address", "macAddress", "code")


def _get_serial(appliance) -> str:
    for attr in _SERIAL_ATTRS:
        val = getattr(appliance, attr, None)
        if val:
            return str(val)
    return ""


def _get_name(appliance) -> str:
    for attr in ("nick_name", "nickName", "model_name", "modelName", "name"):
        val = getattr(appliance, attr, None)
        if val:
            return str(val)
    return "Haier Appliance"


def _get_model(appliance) -> str:
    for attr in ("model_name", "modelName", "model", "typology"):
        val = getattr(appliance, attr, None)
        if val:
            return str(val)
    return "Unknown"


def _get_type(appliance) -> str:
    for attr in ("appliance_type", "applianceType", "type_name", "category"):
        val = getattr(appliance, attr, None)
        if val:
            return str(val).upper()
    return "UNKNOWN"


def _get_attributes(appliance) -> dict:
    """Estrae gli attributi dal device, cercando in attributes e settings."""
    attributes = {}

    raw = getattr(appliance, "attributes", {})
    if isinstance(raw, dict):
        attributes.update(raw)
        params = raw.get("parameters", None)
        if params is not None:
            if isinstance(params, dict):
                attributes.update(params)
            elif hasattr(params, "__iter__"):
                try:
                    attributes.update(dict(params))
                except Exception as e:
                    _LOGGER.debug("Errore lettura parameters: %s", e)
    elif hasattr(raw, "parameters"):
        try:
            attributes.update(dict(raw.parameters))
        except Exception:
            pass

    if hasattr(appliance, "settings"):
        try:
            attributes.update(dict(appliance.settings))
        except Exception as err:
            _LOGGER.error("Errore lettura settings: %s", err)

    return attributes


class HonClient:
    """Gestisce la connessione alle API Haier hOn tramite pyhOn.

    Strategia loop:
    - Manteniamo un singolo event loop dedicato (_hon_loop) che gira su un
      thread di background (_hon_thread).
    - TUTTE le chiamate a pyhOn (setup, update, comandi) vengono eseguite su
      quel loop tramite asyncio.run_coroutine_threadsafe(), così la sessione
      aiohttp non cambia mai loop e non va mai in errore.
    - L'event loop di HA non viene mai bloccato.
    """

    def __init__(self, email: str, password: str) -> None:
        self._email = email
        self._password = password
        self._hon_instance = None
        self._api = None
        self._hon_loop: asyncio.AbstractEventLoop | None = None
        self._hon_thread: threading.Thread | None = None

    # ── Gestione loop dedicato ────────────────────────────────────────────────

    def _start_hon_loop(self) -> None:
        """Avvia il loop dedicato su un thread di background."""
        self._hon_loop = asyncio.new_event_loop()
        self._hon_thread = threading.Thread(
            target=self._hon_loop.run_forever,
            name="haier_hon_loop",
            daemon=True,
        )
        self._hon_thread.start()
        _LOGGER.debug("Loop dedicato hOn avviato su thread '%s'", self._hon_thread.name)

    def _run_on_hon_loop(self, coro) -> Any:
        """Esegue una coroutine sul loop dedicato e aspetta il risultato.

        Chiamare solo da un thread non-loop (es. executor di HA).
        """
        if self._hon_loop is None or not self._hon_loop.is_running():
            raise RuntimeError("Loop dedicato hOn non attivo")
        future = asyncio.run_coroutine_threadsafe(coro, self._hon_loop)
        return future.result(timeout=60)

    def _stop_hon_loop(self) -> None:
        """Ferma il loop dedicato e il thread."""
        if self._hon_loop and self._hon_loop.is_running():
            self._hon_loop.call_soon_threadsafe(self._hon_loop.stop)
        if self._hon_thread and self._hon_thread.is_alive():
            self._hon_thread.join(timeout=10)
        self._hon_loop = None
        self._hon_thread = None

    # ── Setup ─────────────────────────────────────────────────────────────────

    def setup_sync(self) -> None:
        """Setup completo di pyhOn in executor (NON sull'event loop di HA).

        Avvia il loop dedicato, crea l'istanza Hon e completa il login.
        La sessione aiohttp viene creata sul loop dedicato e vi rimane
        legata per tutta la durata del client.
        """
        try:
            from pyhon import Hon
        except ImportError as err:
            raise ImportError("La libreria pyhOn non è installata.") from err

        if self._hon_loop is None or not self._hon_loop.is_running():
            self._start_hon_loop()

        self._hon_instance = Hon(email=self._email, password=self._password)
        _LOGGER.debug("Istanza Hon creata")

        # Login + init sessione aiohttp — sul loop dedicato
        self._api = self._run_on_hon_loop(self._hon_instance.__aenter__())
        _LOGGER.info("Connessione a hOn riuscita per %s", self._email)

    async def async_complete_setup(self) -> None:
        """Verifica che il setup sia andato a buon fine."""
        if self._api is None:
            raise RuntimeError("setup_sync() non ha completato il login hOn")

    def run_command_sync(self, coro) -> Any:
        """Esegue una coroutine di comando sul loop dedicato (sincrono, in executor).

        Usato da climate.py per inviare comandi senza bloccare l'event loop di HA
        e senza il RuntimeError 'Timeout context manager should be used inside a task'.
        """
        return self._run_on_hon_loop(coro)

    # ── Appliances ───────────────────────────────────────────────────────────

    async def async_get_appliances(self) -> list:
        if self._api is None:
            return []
        try:
            return self._api.appliances
        except Exception as err:
            _LOGGER.error("Errore recupero elettrodomestici: %s", err)
            return []

    def _update_appliance_sync(self, appliance) -> None:
        """Aggiorna un appliance sul loop dedicato (sincrono, chiamato in executor)."""

        async def _do_update():
            # Tentativo 1: update() standard
            if hasattr(appliance, "update") and callable(appliance.update):
                try:
                    await appliance.update()
                    return
                except Exception as err:
                    _LOGGER.debug("update() fallito: %s — provo load_*", err or "<no msg>")

            # Tentativo 2: load_attributes / load_commands / load_statistics
            loaded = False
            for method_name in ("load_attributes", "load_commands", "load_statistics"):
                method = getattr(appliance, method_name, None)
                if method and callable(method):
                    try:
                        await method()
                        loaded = True
                        _LOGGER.debug("Fallback OK: %s", method_name)
                    except Exception as err:
                        _LOGGER.debug("Fallback %s fallito: %s", method_name, err)

            if not loaded:
                raise RuntimeError(
                    "Nessun metodo di aggiornamento disponibile — "
                    "verifica la versione di pyhOn installata."
                )

        self._run_on_hon_loop(_do_update())

    def run_command_sync(self, coro) -> Any:
        """Esegue una coroutine pyhOn (es. command.send()) sul loop dedicato.

        Da chiamare in executor — non sull'event loop di HA.
        """
        return self._run_on_hon_loop(coro)

    # ── Re-auth ───────────────────────────────────────────────────────────────

    async def _async_reauth(self) -> bool:
        """Ri-autentica in caso di token scaduto."""
        _LOGGER.info("Tentativo re-autenticazione hOn...")
        try:
            if self._hon_instance is not None:
                hon = self._hon_instance
                self._hon_instance = None
                self._api = None
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self._run_on_hon_loop(hon.__aexit__(None, None, None)),
                    )
                except Exception:
                    pass

            await asyncio.get_event_loop().run_in_executor(None, self.setup_sync)
            _LOGGER.info("Re-autenticazione hOn riuscita")
            return True
        except Exception as err:
            _LOGGER.error("Re-autenticazione hOn fallita: %s", err)
            return False

    # ── Polling dati ──────────────────────────────────────────────────────────

    async def async_get_appliances_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        appliances = await self.async_get_appliances()
        _LOGGER.debug("Trovati %d dispositivi hOn", len(appliances))

        for appliance in appliances:
            try:
                last_err = None
                for attempt in range(3):
                    try:
                        await asyncio.get_event_loop().run_in_executor(
                            None, self._update_appliance_sync, appliance
                        )
                        last_err = None
                        break
                    except Exception as err:
                        last_err = err
                        err_str = str(err).lower()
                        is_server_err = any(k in err_str for k in (
                            "personaccountid", "internal server error",
                            "500", "503", "unauthorized", "401", "token",
                        ))
                        if is_server_err and attempt < 2:
                            wait = 5 * (attempt + 1)
                            _LOGGER.warning(
                                "Errore server Haier (tentativo %d/3), riprovo tra %ds: %s",
                                attempt + 1, wait, err,
                            )
                            await asyncio.sleep(wait)
                        else:
                            break

                if last_err is not None:
                    raise last_err

                appliance_id = (
                    getattr(appliance, "unique_id", None)
                    or _get_serial(appliance)
                    or str(id(appliance))
                )
                attributes = _get_attributes(appliance)
                name = _get_name(appliance)
                app_type = _get_type(appliance)

                data[appliance_id] = {
                    "appliance": appliance,
                    "type": app_type,
                    "name": name,
                    "model": _get_model(appliance),
                    "serial": _get_serial(appliance),
                    "attributes": attributes,
                    "settings": dict(appliance.settings) if hasattr(appliance, "settings") else {},
                }
                _LOGGER.debug(
                    "Aggiornato '%s' (type=%s, id=%s) — %d attributi",
                    name, app_type, appliance_id, len(attributes),
                )

            except Exception as err:
                err_str = str(err).lower()
                is_auth_err = any(k in err_str for k in (
                    "personaccountid", "unauthorized", "401", "token", "auth",
                ))
                _LOGGER.warning(
                    "Errore aggiornamento '%s' (type=%s): %s",
                    _get_name(appliance), _get_type(appliance), err,
                    exc_info=True,
                )
                if is_auth_err:
                    _LOGGER.warning("Errore auth Haier — avvio re-autenticazione")
                    await self._async_reauth()
                    break

        _LOGGER.info("Caricati %d dispositivi hOn con dati", len(data))
        return data

    # ── Chiusura ──────────────────────────────────────────────────────────────

    async def async_close(self) -> None:
        if self._hon_instance is not None:
            hon = self._hon_instance
            self._hon_instance = None
            self._api = None
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._run_on_hon_loop(hon.__aexit__(None, None, None)),
                )
            except Exception:
                pass
        self._stop_hon_loop()
