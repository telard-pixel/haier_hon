"""Switch per Haier hOn - accensione e pausa lavatrice/asciugatrice."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base_entity import HonBaseEntity
from .const import APPLIANCE_WASH_GROUP, DOMAIN, WM_ATTR_STATUS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = []
    for appliance_id, data in coordinator.data.items():
        if data.get("type") in APPLIANCE_WASH_GROUP:
            entities.append(HonWashingMachineSwitch(coordinator, appliance_id))
            # Aggiunge switch pausa solo se il device supporta pauseProgram + resumeProgram
            appliance = data.get("appliance")
            if appliance and hasattr(appliance, "commands"):
                cmds = appliance.commands if isinstance(appliance.commands, dict) else {}
                if "pauseProgram" in cmds and "resumeProgram" in cmds:
                    entities.append(HonWashingMachinePauseSwitch(coordinator, appliance_id))
            _LOGGER.info("Aggiunto switch: %s", data.get("name"))
    async_add_entities(entities)


class HonWashingMachineSwitch(HonBaseEntity, SwitchEntity):
    """Switch per alimentazione lavatrice (on/off).

    FIX: il comando 'settings' della WM HW80-B14959TU1IT non espone
    'onOffStatus' (ha solo category/httpEndpoint/mqttEndpoint).
    Lo stato ON/OFF si determina da 'machMode':
        "0" = In attesa / Standby → spenta
        qualsiasi altro valore    → accesa/in ciclo
    Per avviare si usa startProgram.send() direttamente (onOffStatus
    NON è un parametro di startProgram su questo modello).
    Per spegnere si usa stopProgram.onOffStatus = "0" (confermato dai diagnostics).
    """

    _attr_icon = "mdi:power"

    def __init__(self, coordinator, appliance_id: str) -> None:
        super().__init__(coordinator, appliance_id)
        device_name = self._appliance_data.get("name", "Lavatrice")
        self._attr_unique_id = f"{appliance_id}_power"
        self._attr_name = f"{device_name} - Alimentazione"

    @property
    def is_on(self) -> bool:
        """Stato acceso/spento.

        FIX: settings.onOffStatus NON esiste per questa WM.
        Usiamo machMode: "0" = standby/spenta, qualsiasi altro = accesa.
        """
        val = self._get_attr(WM_ATTR_STATUS, "0")  # WM_ATTR_STATUS = "machMode"
        return str(val) != "0"

    async def async_turn_on(self, **kwargs) -> None:
        """Avvia la lavatrice tramite startProgram.

        FIX: 'onOffStatus' NON è un parametro di startProgram su questo modello.
        pyhOn avvia il ciclo con i parametri correnti (programma già selezionato
        tramite il select entity) semplicemente chiamando command.send().
        """
        appliance = self._appliance
        if not appliance:
            _LOGGER.error("Switch: Appliance non disponibile")
            return
        try:
            commands = appliance.commands if isinstance(appliance.commands, dict) else {}
            command = commands.get("startProgram")
            if not command:
                _LOGGER.error(
                    "Switch: Comando 'startProgram' non trovato. Disponibili: %s",
                    list(commands.keys()),
                )
                return
            await command.send()
            _LOGGER.info("Switch ON: startProgram inviato")
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Switch ON: Errore: %s", err, exc_info=True)

    async def async_turn_off(self, **kwargs) -> None:
        """Spegne la lavatrice tramite stopProgram.onOffStatus = "0".

        Confermato dai diagnostics: stopProgram ha il parametro 'onOffStatus'.
        """
        appliance = self._appliance
        if not appliance:
            _LOGGER.error("Switch: Appliance non disponibile")
            return
        try:
            commands = appliance.commands if isinstance(appliance.commands, dict) else {}
            command = commands.get("stopProgram")
            if command:
                if hasattr(command, "parameters") and "onOffStatus" in command.parameters:
                    command.parameters["onOffStatus"].value = "0"
                await command.send()
                _LOGGER.info("Switch OFF: stopProgram inviato")
            else:
                # Fallback: prova con settings se disponibile (non atteso su questo modello)
                _LOGGER.error(
                    "Switch OFF: Comando 'stopProgram' non trovato. Disponibili: %s",
                    list(commands.keys()),
                )
                return
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Switch OFF: Errore: %s", err, exc_info=True)


class HonWashingMachinePauseSwitch(HonBaseEntity, SwitchEntity):
    """Switch per mettere in pausa / riprendere il programma lavatrice.

    Usa pauseProgram e resumeProgram — entrambi confermati dai diagnostics
    con parametro 'pause'.
    """

    _attr_icon = "mdi:pause-circle"

    def __init__(self, coordinator, appliance_id: str) -> None:
        super().__init__(coordinator, appliance_id)
        device_name = self._appliance_data.get("name", "Lavatrice")
        self._attr_unique_id = f"{appliance_id}_pause"
        self._attr_name = f"{device_name} - Pausa"

    @property
    def is_on(self) -> bool:
        """True = in pausa. machMode "2" = In pausa (dal WM_STATE_MAP)."""
        val = self._get_attr(WM_ATTR_STATUS, "0")  # WM_ATTR_STATUS = "machMode"
        return str(val) == "2"

    async def async_turn_on(self, **kwargs) -> None:
        """Mette in pausa il programma corrente."""
        appliance = self._appliance
        if not appliance:
            return
        try:
            commands = appliance.commands if isinstance(appliance.commands, dict) else {}
            command = commands.get("pauseProgram")
            if not command:
                _LOGGER.error("Pausa: comando 'pauseProgram' non trovato")
                return
            if hasattr(command, "parameters") and "pause" in command.parameters:
                command.parameters["pause"].value = "1"
            await command.send()
            _LOGGER.info("Pausa: programma messo in pausa")
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Pausa ON: Errore: %s", err, exc_info=True)

    async def async_turn_off(self, **kwargs) -> None:
        """Riprende il programma in pausa."""
        appliance = self._appliance
        if not appliance:
            return
        try:
            commands = appliance.commands if isinstance(appliance.commands, dict) else {}
            command = commands.get("resumeProgram")
            if not command:
                _LOGGER.error("Pausa: comando 'resumeProgram' non trovato")
                return
            if hasattr(command, "parameters") and "pause" in command.parameters:
                command.parameters["pause"].value = "0"
            await command.send()
            _LOGGER.info("Pausa: programma ripreso")
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Pausa OFF: Errore: %s", err, exc_info=True)
