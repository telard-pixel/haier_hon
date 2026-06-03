import logging
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configura i sensori basandosi sul coordinator."""
    coordinator = hass.data["haier_hon"][entry.entry_id]
    entities = []

    for appliance_id in coordinator.data.keys():
        entities.append(HaierCompressorFrequencySensor(coordinator, appliance_id))
        entities.append(HaierTemperatureSensor(coordinator, appliance_id, "internal"))
        entities.append(HaierTemperatureSensor(coordinator, appliance_id, "external"))

    async_add_entities(entities)

class HaierBaseSensor(CoordinatorEntity, SensorEntity):
    """Classe base per tutti i sensori Haier."""

    def __init__(self, coordinator, appliance_id):
        super().__init__(coordinator)
        self._appliance_id = appliance_id

    @property
    def available(self) -> bool:
        """Il sensore è disponibile se l'ultimo aggancio del coordinatore è andato a buon fine."""
        return self.coordinator.last_update_success and self._appliance_id in self.coordinator.data

    @property
    def _device_data(self):
        """Prende i dati pre-caricati dal coordinatore senza fare chiamate HTTP."""
        return self.coordinator.data.get(self._appliance_id, {})


class HaierCompressorFrequencySensor(HaierBaseSensor):
    """Sensore frequenza compressore (Hz)."""

    def __init__(self, coordinator, appliance_id):
        super().__init__(coordinator, appliance_id)
        self._attr_name = "Haier Frequenza Compressore"
        self._attr_unique_id = f"haier_{appliance_id}_compressor_freq"
        self._attr_native_unit_of_measurement = "Hz"
        if hasattr(SensorDeviceClass, 'FREQUENCY'):
            self._attr_device_class = SensorDeviceClass.FREQUENCY

    @property
    def native_value(self):
        if not self.available:
            return None
        hz_value = self._device_data.get("shadow", {}).get("parameters", {}).get("compressorFrequency", {}).get("value")
        try:
            return float(hz_value) if hz_value is not None else None
        except (ValueError, TypeError):
            return None


class HaierTemperatureSensor(HaierBaseSensor):
    """Sensore temperature."""

    def __init__(self, coordinator, appliance_id, temp_type):
        super().__init__(coordinator, appliance_id)
        self._temp_type = temp_type
        self._attr_native_unit_of_measurement = "°C"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        
        if temp_type == "internal":
            self._attr_name = "Haier Temperatura Interna"
            self._attr_unique_id = f"haier_{appliance_id}_temp_int"
        else:
            self._attr_name = "Haier Temperatura Esterna"
            self._attr_unique_id = f"haier_{appliance_id}_temp_ext"

    @property
    def native_value(self):
        if not self.available:
            return None
        param_key = "tempIndoor" if self._temp_type == "internal" else "tempOutdoor"
        temp_value = self._device_data.get("shadow", {}).get("parameters", {}).get(param_key, {}).get("value")
        try:
            return float(temp_value) if temp_value is not None else None
        except (ValueError, TypeError):
            return None