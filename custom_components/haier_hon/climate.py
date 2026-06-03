import logging
import asyncio
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configura l'entità climate basandosi sul coordinator."""
    coordinator = hass.data["haier_hon"][entry.entry_id]
    async_add_entities([HaierClimateEntity(coordinator, aid) for aid in coordinator.data.keys()])

class HaierClimateEntity(CoordinatorEntity, ClimateEntity):
    """Rappresentazione del condizionatore Haier hOn."""

    def __init__(self, coordinator, appliance_id):
        super().__init__(coordinator)
        self._appliance_id = appliance_id
        
        self._attr_name = "Condizionatore Haier"
        self._attr_unique_id = f"haier_{appliance_id}_climate"
        self._attr_temperature_unit = "°C"
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
        )
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.FAN_ONLY]
        self._attr_fan_modes = ["auto", "low", "medium", "high"]

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._appliance_id in self.coordinator.data

    @property
    def _device_data(self):
        return self.coordinator.data.get(self._appliance_id, {})

    @property
    def hvac_mode(self) -> HVACMode:
        if not self.available:
            return HVACMode.OFF
        params = self._device_data.get("shadow", {}).get("parameters", {})
        on_off = params.get("onOffStatus", {}).get("value")
        
        if on_off == 0 or on_off is None:
            return HVACMode.OFF
            
        mode = params.get("machMode", {}).get("value")
        mapping = {1: HVACMode.COOL, 2: HVACMode.HEAT, 4: HVACMode.FAN_ONLY}
        return mapping.get(mode, HVACMode.OFF)

    @property
    def target_temperature(self) -> float:
        if not self.available:
            return 24.0
        temp = self._device_data.get("shadow", {}).get("parameters", {}).get("tempSel", {}).get("value")
        return float(temp) if temp is not None else 24.0

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Invia il cambio modalità ed esegue un refresh forzato immediato."""
        # Recuperiamo il client API dal file originale (immagazzinato dentro l'oggetto coordinatore o simile)
        # Nota: assumiamo che tu possa accedere al client o ricrearlo, o che sia accessibile tramite coordinator
        # Per sicurezza usiamo il client associato se memorizzato, oppure modificalo in base a dove risiede il client API
        api_client = self.coordinator.hass.data["haier_hon"][self.coordinator.config_entry.entry_id].api_client
        
        try:
            async with asyncio.timeout(10):
                if hvac_mode == HVACMode.OFF:
                    await api_client.set_device_status(self._appliance_id, {"onOffStatus": 0})
                else:
                    mode_mapping = {HVACMode.COOL: 1, HVACMode.HEAT: 2, HVACMode.FAN_ONLY: 4}
                    mach_mode = mode_mapping.get(hvac_mode, 1)
                    await api_client.set_device_status(
                        self._appliance_id, {"onOffStatus": 1, "machMode": mach_mode}
                    )
                # Diciamo al coordinatore di aggiornare immediatamente i dati per mostrare lo stato aggiornato
                await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Errore nell'invio del comando HVAC: %s", err)