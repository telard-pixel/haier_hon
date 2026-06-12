"""Select per Haier hOn - selezione programma lavatrice."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base_entity import HonBaseEntity
from .const import APPLIANCE_WASH_GROUP, DOMAIN

_LOGGER = logging.getLogger(__name__)

PROGRAM_MAP = {
    "0": "Cotone", "1": "Sintetici", "2": "Mix", "3": "Delicati",
    "4": "Lana", "5": "Seta/Mano", "6": "Rapido 14'", "7": "Rapido 30'",
    "8": "Rapido 44'", "9": "Sport", "10": "Scuro", "11": "Baby",
    "12": "Igiene+", "13": "Vapore", "14": "Centrifuga", "15": "Risciacquo+",
    "17": "Auto", "18": "Antiodore", "19": "Allergy Care", "20": "Piumoni",
    "21": "Jeans", "22": "Outdoor",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    # FIX: accesso coerente alla struttura hass.data[DOMAIN][entry_id]["coordinator"]
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = entry_data["coordinator"]
    client = entry_data["client"]
    entities = []
    for appliance_id, data in coordinator.data.items():
        if data.get("type") in APPLIANCE_WASH_GROUP:
            entities.append(HonProgramSelect(coordinator, appliance_id, client))
            _LOGGER.info("Aggiunto select programma: %s", data.get("name"))
    async_add_entities(entities)


class HonProgramSelect(HonBaseEntity, SelectEntity):
    """Select per la selezione del programma lavatrice/asciugatrice."""

    _attr_icon = "mdi:format-list-bulleted"

    def __init__(self, coordinator, appliance_id: str, client=None) -> None:
        super().__init__(coordinator, appliance_id, client)
        device_name = self._appliance_data.get("name", "Lavatrice")
        self._attr_unique_id = f"{appliance_id}_program"
        self._attr_name = f"{device_name} - Programma"

        self._program_map: dict[str, str] = {}
        appliance = self._appliance
        if appliance is not None:
            self._program_map = self._load_programs(appliance)
        if not self._program_map:
            self._program_map = dict(PROGRAM_MAP)

        self._program_reverse: dict[str, str] = {v: k for k, v in self._program_map.items()}
        self._attr_options = list(self._program_reverse.keys())

    @staticmethod
    def _load_programs(appliance) -> dict[str, str]:
        try:
            cmd = None
            if hasattr(appliance, "commands") and isinstance(appliance.commands, dict):
                cmd = appliance.commands.get("startProgram")
            if cmd is None:
                return {}
            params = getattr(cmd, "parameters", None)
            if params is None:
                return {}
            prog_param = params.get("program") if "program" in params else params.get("prCode")
            if prog_param is None:
                return {}
            values = None
            for attr in ("values", "value_list", "options"):
                raw = getattr(prog_param, attr, None)
                if isinstance(raw, dict):
                    values = raw
                    break
                if isinstance(raw, (list, tuple)):
                    values = {str(v): str(v) for v in raw}
                    break
            if not values:
                return {}
            return {
                str(code): PROGRAM_MAP.get(str(code), str(label) if label else str(code))
                for code, label in values.items()
            }
        except Exception as err:
            _LOGGER.debug("Errore caricamento programmi dinamici: %s", err)
            return {}

    @property
    def current_option(self) -> str | None:
        # FIX: controllare esplicitamente is not None invece di usare 'or' che scarta 0
        code = None
        for key in ("startProgram.program", "startProgram.prCode", "prCode"):
            val = self._get_attr(key)
            if val is not None:
                code = val
                break
        
        if code is None:
            return None
        return self._program_map.get(str(code))

    async def async_select_option(self, option: str) -> None:
        code = self._program_reverse.get(option)
        if code is None:
            raise HomeAssistantError(f"Select: programma '{option}' non trovato nella mappa")
        appliance = self._appliance
        client = self._hon_client
        if not appliance or not client:
            raise HomeAssistantError("Select: appliance o client non disponibile")
        try:
            def _do():
                async def _inner():
                    commands = appliance.commands if isinstance(appliance.commands, dict) else {}
                    command = commands.get("startProgram")
                    if not command:
                        raise RuntimeError(
                            f"Comando 'startProgram' non trovato. Disponibili: {list(commands.keys())}"
                        )
                    params = getattr(command, "parameters", {})
                    param_name = (
                        "program" if "program" in params
                        else "prCode" if "prCode" in params
                        else None
                    )
                    if param_name is None:
                        raise RuntimeError(
                            f"Parametro 'program'/'prCode' non trovato. Disponibili: {list(params.keys())}"
                        )
                    command.parameters[param_name].value = code
                    await command.send()

                client.run_command_sync(_inner())

            await self.hass.async_add_executor_job(_do)
            _LOGGER.info("Select: programma '%s' (code=%s) inviato", option, code)
            await self._async_request_command_refresh()
        except Exception as err:
            _LOGGER.error("Select: errore selezione programma '%s': %s", option, err, exc_info=True)
            raise HomeAssistantError(
                f"Select: errore selezione programma '{option}': {err}"
            ) from err
