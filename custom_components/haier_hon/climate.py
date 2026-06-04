"""Climate entity per Haier hOn - condizionatore AS35PBPHRA-PRE."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    APPLIANCE_AC,
    DOMAIN,
    AC_MODE_MAP,
    AC_MODE_MAP_REVERSE,
    AC_FAN_MAP,
    AC_FAN_MAP_REVERSE,
)
from .base_entity import HonBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configura l'entità climate basandosi sul coordinator."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    
    entities = [
        HaierClimateEntity(coordinator, aid, client)
        for aid, data in coordinator.data.items()
        if data.get("type") == APPLIANCE_AC
    ]
    async_add_entities(entities)


class HaierClimateEntity(HonBaseEntity, ClimateEntity):
    """Rappresentazione del condizionatore Haier hOn."""

    def __init__(self, coordinator, appliance_id: str, client) -> None:
        super().__init__(coordinator, appliance_id)
        device_name = self._appliance_data.get("name", "Condizionatore")
        self._attr_name = device_name
        self._attr_unique_id = f"{appliance_id}_climate"

        self._attr_temperature_unit = "°C"
        self._attr_target_temperature_step = 1.0
        
        # FIX: Forziamo l'uso degli Enum nativi di HA per evitare la visualizzazione dei numeri nel frontend
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.AUTO,
            HVACMode.COOL,
            HVACMode.DRY,
            HVACMode.HEAT,
            HVACMode.FAN_ONLY,
        ]
        self._attr_fan_modes = list(AC_FAN_MAP.keys())

        # Configurazione riferimenti API protetti
        self._appliance_id = appliance_id
        self._api_client = client
        self._cached_appliance = None

    @property
    def appliance_obj(self) -> Any:
        """Risolve l'oggetto appliance di pyhOn tramite una catena di fallback sicura."""
        if self._cached_appliance is not None:
            return self._cached_appliance

        if hasattr(self, "_appliance") and self._appliance is not None:
            self._cached_appliance = self._appliance
            return self._appliance

        if hasattr(self, "_appliance_data") and isinstance(self._appliance_data, dict):
            if "appliance" in self._appliance_data:
                self._cached_appliance = self._appliance_data["appliance"]
                return self._cached_appliance

        client = self._api_client
        for attr_name in ("_hon", "hon", "_api", "api", "appliances"):
            if hasattr(client, attr_name):
                attr = getattr(client, attr_name)
                if hasattr(attr, "appliances"):
                    apps = attr.appliances
                    if isinstance(apps, list):
                        for app in apps:
                            if getattr(app, "mac_address", None) == self._appliance_id:
                                self._cached_appliance = app
                                return app
                    elif isinstance(apps, dict) and self._appliance_id in apps:
                        self._cached_appliance = apps[self._appliance_id]
                        return self._cached_appliance
                if attr_name == "appliances":
                    if isinstance(attr, dict) and self._appliance_id in attr:
                        self._cached_appliance = attr[self._appliance_id]
                        return self._cached_appliance
                    elif isinstance(attr, list):
                        for app in attr:
                            if getattr(app, "mac_address", None) == self._appliance_id:
                                self._cached_appliance = app
                                return app
        return None

    def _get_hon_mode_code(self, hvac_mode: HVACMode) -> str:
        """Traduce in modo resiliente un HVACMode di HA nel codice numerico hOn."""
        target_str = hvac_mode.value if hasattr(hvac_mode, "value") else str(hvac_mode)
        
        for k, v in AC_MODE_MAP.items():
            k_str = k.value if hasattr(k, "value") else str(k)
            if k_str == target_str:
                return str(v)
            if str(k) == target_str:
                return str(v)

        for k, v in AC_MODE_MAP_REVERSE.items():
            v_str = v.value if hasattr(v, "value") else str(v)
            if v_str == target_str:
                return str(k)

        fallback = {"auto": "1", "cool": "2", "dry": "3", "heat": "4", "fan_only": "5"}
        return fallback.get(target_str, "1")

    def _get_ha_hvac_mode(self, hon_code: str) -> HVACMode:
        """Traduce in modo resiliente il codice numerico hOn in un HVACMode standard."""
        code_str = str(hon_code)
        
        if code_str in AC_MODE_MAP_REVERSE:
            val = AC_MODE_MAP_REVERSE[code_str]
            if isinstance(val, HVACMode):
                return val
            try:
                return HVACMode(str(val).lower())
            except ValueError:
                pass

        for k, v in AC_MODE_MAP.items():
            if str(v) == code_str:
                if isinstance(k, HVACMode):
                    return k
                try:
                    return HVACMode(str(k).lower())
                except ValueError:
                    pass

        fallback = {"1": HVACMode.AUTO, "2": HVACMode.COOL, "3": HVACMode.DRY, "4": HVACMode.HEAT, "5": HVACMode.FAN_ONLY}
        return fallback.get(code_str, HVACMode.COOL)

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Ritorna le funzionalità supportate con i nuovi standard di Home Assistant."""
        return (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

    @property
    def hvac_mode(self) -> HVACMode:
        """Ritorna la modalità HVAC corrente standard."""
        on_off = self._get_attr("onOffStatus")
        if str(on_off) == "0" or on_off == 0:
            return HVACMode.OFF

        program = self._get_attr("screenDisplayStatus") or self._get_attr("machMode") or "1"
        return self._get_ha_hvac_mode(str(program))

    @property
    def current_temperature(self) -> float | None:
        """Ritorna la temperatura interna corrente."""
        val = self._get_attr("tempIndoor")
        return float(val) if val is not None else None

    @property
    def target_temperature(self) -> float | None:
        """Ritorna la temperatura target impostata."""
        val = self._get_attr("tempSel")
        return float(val) if val is not None else None

    @property
    def fan_mode(self) -> str | None:
        """Ritorna la modalità di ventilazione corrente."""
        speed = self._get_attr("windSpeed")
        return AC_FAN_MAP.get(str(speed), "auto")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Imposta la modalità HVAC inviando i comandi corretti sul loop sincrono."""
        appliance = self.appliance_obj
        client = self._api_client
        if not appliance or not client:
            return

        try:
            if hvac_mode == HVACMode.OFF:
                await self._send_command_in_executor(client, appliance, {"onOffStatus": "0"})
            else:
                mode_key = self._get_hon_mode_code(hvac_mode)
                params = {
                    "onOffStatus": "1",
                    "machMode": mode_key
                }
                await self._send_command_in_executor(client, appliance, params)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Climate: errore set_hvac_mode: %s", err, exc_info=True)

    async def async_turn_on(self) -> None:
        """Azione esplicita di accensione richiamata da Home Assistant."""
        await self.async_set_hvac_mode(HVACMode.COOL)

    async def async_turn_off(self) -> None:
        """Azione esplicita di spegnimento richiamata da Home Assistant."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Imposta la temperatura target."""
        temp = kwargs.get("temperature")
        if temp is None:
            return
        appliance = self.appliance_obj
        client = self._api_client
        if not appliance or not client:
            return
        try:
            await self._send_command_in_executor(client, appliance, {"tempSel": str(int(temp))})
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Climate: errore set_temperature: %s", err, exc_info=True)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Invia la velocità ventola."""
        appliance = self.appliance_obj
        client = self._api_client
        if not appliance or not client:
            return
        try:
            speed_key = "0"
            for k, v in AC_FAN_MAP.items():
                if str(v) == str(fan_mode):
                    speed_key = str(k)
                    break
            if speed_key == "0" and fan_mode in AC_FAN_MAP_REVERSE:
                speed_key = str(AC_FAN_MAP_REVERSE[fan_mode])

            await self._send_command_in_executor(client, appliance, {"windSpeed": speed_key})
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Climate: errore set_fan_mode: %s", err, exc_info=True)

    async def _send_command_in_executor(self, client, appliance, params: dict) -> None:
        """Invia un comando settings tramite pyhOn sul loop dedicato (in executor)."""
        def _do_send():
            async def _inner():
                commands = appliance.commands if isinstance(appliance.commands, dict) else {}
                command = commands.get("settings")
                if command is None:
                    raise RuntimeError("Comando 'settings' non trovato sul dispositivo AC")
                for key, value in params.items():
                    if hasattr(command, "parameters") and key in command.parameters:
                        command.parameters[key].value = value
                    else:
                        _LOGGER.warning("Climate: parametro '%s' non trovato nel comando settings", key)
                await command.send()

            client.run_command_sync(_inner())

        await self.hass.async_add_executor_job(_do_send)