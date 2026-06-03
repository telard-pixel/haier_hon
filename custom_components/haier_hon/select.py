"""Select per Haier hOn - selezione programma lavatrice."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base_entity import HonBaseEntity
from .const import APPLIANCE_WASH_GROUP, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Programmi lavatrice - Numeri di default
# Se il tuo modello ha programmi diversi, controlla startProgram.program nel log
PROGRAM_MAP = {
    "0": "Cotone",
    "1": "Sintetici",
    "2": "Mix",
    "3": "Delicati",
    "4": "Lana",
    "5": "Seta/Mano",
    "6": "Rapido 14'",
    "7": "Rapido 30'",
    "8": "Rapido 44'",
    "9": "Sport",
    "10": "Scuro",
    "11": "Baby",
    "12": "Igiene+",
    "13": "Vapore",
    "14": "Centrifuga",
    "15": "Risciacquo+",
    "17": "Auto",
    "18": "Antiodore",
    "19": "Allergy Care",
    "20": "Piumoni",
    "21": "Jeans",
    "22": "Outdoor",
}
PROGRAM_MAP_REVERSE = {v: k for k, v in PROGRAM_MAP.items()}  # Usato come fallback statico


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = []
    for appliance_id, data in coordinator.data.items():
        if data.get("type") in APPLIANCE_WASH_GROUP:
            entities.append(HonProgramSelect(coordinator, appliance_id))
            _LOGGER.info("Aggiunto select programma: %s", data.get("name"))
    async_add_entities(entities)


class HonProgramSelect(HonBaseEntity, SelectEntity):
    """Select per la selezione del programma lavatrice/asciugatrice."""
    
    _attr_icon = "mdi:format-list-bulleted"

    def __init__(self, coordinator, appliance_id: str) -> None:
        super().__init__(coordinator, appliance_id)
        device_name = self._appliance_data.get("name", "Lavatrice")
        self._attr_unique_id = f"{appliance_id}_program"
        self._attr_name = f"{device_name} - Programma"

        # Prova a caricare i programmi dinamicamente dall'appliance
        self._program_map: dict[str, str] = {}
        self._program_reverse: dict[str, str] = {}
        appliance = self._appliance
        if appliance is not None:
            self._program_map = self._load_programs(appliance)
        
        # Fallback alla mappa statica se il dispositivo non ha fornito programmi
        if not self._program_map:
            self._program_map = dict(PROGRAM_MAP)
        
        self._program_reverse = {v: k for k, v in self._program_map.items()}
        self._attr_options = list(self._program_reverse.keys())

    @staticmethod
    def _load_programs(appliance) -> dict[str, str]:
        """Tenta di caricare i programmi disponibili dall'appliance pyhOn."""
        try:
            cmd = None
            if hasattr(appliance, "commands") and isinstance(appliance.commands, dict):
                cmd = appliance.commands.get("startProgram")
            if cmd is None:
                return {}
            
            params = getattr(cmd, "parameters", None)
            if params is None:
                return {}
            
            # Cerca il parametro "program" o "prCode"
            prog_param = params.get("program") or params.get("prCode")
            if prog_param is None:
                return {}
            
            # Prova a estrarre i valori disponibili
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
            
            result: dict[str, str] = {}
            for code, label in values.items():
                # Se il label è già una stringa leggibile, usalo; altrimenti usa il fallback
                label_str = str(label) if label else str(code)
                result[str(code)] = PROGRAM_MAP.get(str(code), label_str)
            return result

        except Exception as err:
            _LOGGER.debug("Errore caricamento programmi dinamici: %s", err)
            return {}

    @property
    def current_option(self) -> str | None:
        """Legge il programma attuale."""
        code = self._get_attr("startProgram.program")
        if code is None:
            code = self._get_attr("startProgram.prCode")
        if code is None:
            code = self._get_attr("prCode")
        if code is None:
            return None
        return self._program_map.get(str(code))

    async def async_select_option(self, option: str) -> None:
        """Seleziona un nuovo programma."""
        code = self._program_reverse.get(option)
        if code is None:
            _LOGGER.error("Select: Programma '%s' non trovato nella mappa", option)
            return
        
        appliance = self._appliance
        if not appliance:
            _LOGGER.error("Select: Appliance non disponibile")
            return
        
        try:
            command = appliance.commands.get("startProgram")
            if not command:
                _LOGGER.error(
                    "Select: Comando 'startProgram' non trovato. "
                    "Comandi disponibili: %s",
                    list(appliance.commands.keys())
                )
                return
            
            param_name = None
            if hasattr(command, "parameters"):
                if "program" in command.parameters:
                    param_name = "program"
                elif "prCode" in command.parameters:
                    param_name = "prCode"
            
            if param_name is None:
                _LOGGER.error(
                    "Select: Parametro 'program' o 'prCode' non trovato. "
                    "Parametri disponibili: %s",
                    list(command.parameters.keys()) if hasattr(command, "parameters") else "nessuno"
                )
                return
            
            command.parameters[param_name].value = code
            _LOGGER.info(
                "Select: Impostato startProgram.%s = %s (%s)",
                param_name, code, option
            )
            await command.send()
            _LOGGER.info("Select: Comando startProgram inviato per programma '%s'", option)
            await self.coordinator.async_request_refresh()
            
        except Exception as err:
            _LOGGER.error(
                "Select: Errore durante selezione programma '%s': %s",
                option, err,
                exc_info=True
            )