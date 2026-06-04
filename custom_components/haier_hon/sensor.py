"""Sensori per Haier hOn - temperature, compressore, lavatrice."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base_entity import HonBaseEntity
from .const import (
    APPLIANCE_AC,
    APPLIANCE_WASH_GROUP,
    DOMAIN,
    AC_ATTR_COMPRESSOR_FREQ,
    AC_ATTR_CURRENT_TEMP,
    AC_ATTR_OUTDOOR_TEMP,
    AC_ATTR_HUMIDITY_INDOOR,
    AC_ATTR_TOTAL_ENERGY,
    WM_ATTR_STATUS,
    WM_ATTR_REMAINING,
    WM_ATTR_TOTAL_WASH,
    WM_ATTR_TOTAL_WATER,
    WM_ATTR_TOTAL_ENERGY,
    WM_ATTR_CURRENT_ENERGY,
    WM_ATTR_CURRENT_WATER,
    WM_STATE_MAP,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configura i sensori basandosi sul coordinator."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = []

    for appliance_id, data in coordinator.data.items():
        app_type = data.get("type", "")

        if app_type == APPLIANCE_AC:
            entities += [
                HonNumericSensor(
                    coordinator, appliance_id,
                    attr_key=AC_ATTR_COMPRESSOR_FREQ,
                    name="Frequenza Compressore",
                    unique_suffix="compressor_freq",
                    unit="Hz",
                    device_class=SensorDeviceClass.FREQUENCY if hasattr(SensorDeviceClass, "FREQUENCY") else None,
                    state_class=SensorStateClass.MEASUREMENT,
                ),
                HonNumericSensor(
                    coordinator, appliance_id,
                    attr_key=AC_ATTR_CURRENT_TEMP,
                    name="Temperatura Interna",
                    unique_suffix="temp_indoor",
                    unit="°C",
                    device_class=SensorDeviceClass.TEMPERATURE,
                    state_class=SensorStateClass.MEASUREMENT,
                ),
                HonNumericSensor(
                    coordinator, appliance_id,
                    attr_key=AC_ATTR_OUTDOOR_TEMP,
                    name="Temperatura Esterna",
                    unique_suffix="temp_outdoor",
                    unit="°C",
                    device_class=SensorDeviceClass.TEMPERATURE,
                    state_class=SensorStateClass.MEASUREMENT,
                ),
                HonNumericSensor(
                    coordinator, appliance_id,
                    attr_key=AC_ATTR_HUMIDITY_INDOOR,
                    name="Umidità Interna",
                    unique_suffix="humidity_indoor",
                    unit="%",
                    device_class=SensorDeviceClass.HUMIDITY,
                    state_class=SensorStateClass.MEASUREMENT,
                ),
                HonNumericSensor(
                    coordinator, appliance_id,
                    attr_key=AC_ATTR_TOTAL_ENERGY,
                    name="Energia Totale",
                    unique_suffix="total_energy",
                    unit="kWh",
                    device_class=SensorDeviceClass.ENERGY,
                    state_class=SensorStateClass.TOTAL_INCREASING,
                ),
            ]

        elif app_type in APPLIANCE_WASH_GROUP:
            entities += [
                HonWMStateSensor(coordinator, appliance_id),
                HonNumericSensor(
                    coordinator, appliance_id,
                    attr_key=WM_ATTR_REMAINING,
                    name="Tempo Rimanente",
                    unique_suffix="remaining",
                    unit="min",
                    device_class=SensorDeviceClass.DURATION if hasattr(SensorDeviceClass, "DURATION") else None,
                    state_class=SensorStateClass.MEASUREMENT,
                ),
                HonNumericSensor(
                    coordinator, appliance_id,
                    attr_key=WM_ATTR_TOTAL_WASH,
                    name="Cicli Totali",
                    unique_suffix="total_wash",
                    unit=None,
                    device_class=None,
                    state_class=SensorStateClass.TOTAL_INCREASING,
                ),
                HonNumericSensor(
                    coordinator, appliance_id,
                    attr_key=WM_ATTR_TOTAL_WATER,
                    name="Acqua Totale",
                    unique_suffix="total_water",
                    unit="L",
                    device_class=SensorDeviceClass.WATER if hasattr(SensorDeviceClass, "WATER") else None,
                    state_class=SensorStateClass.TOTAL_INCREASING,
                ),
                HonNumericSensor(
                    coordinator, appliance_id,
                    attr_key=WM_ATTR_TOTAL_ENERGY,
                    name="Energia Totale",
                    unique_suffix="total_energy_wm",
                    unit="kWh",
                    device_class=SensorDeviceClass.ENERGY,
                    state_class=SensorStateClass.TOTAL_INCREASING,
                ),
                HonNumericSensor(
                    coordinator, appliance_id,
                    attr_key=WM_ATTR_CURRENT_ENERGY,
                    name="Energia Ciclo",
                    unique_suffix="current_energy",
                    unit="kWh",
                    device_class=SensorDeviceClass.ENERGY,
                    state_class=SensorStateClass.TOTAL,
                ),
                HonNumericSensor(
                    coordinator, appliance_id,
                    attr_key=WM_ATTR_CURRENT_WATER,
                    name="Acqua Ciclo",
                    unique_suffix="current_water",
                    unit="L",
                    device_class=SensorDeviceClass.WATER if hasattr(SensorDeviceClass, "WATER") else None,
                    state_class=SensorStateClass.TOTAL,
                ),
            ]

    async_add_entities(entities)


class HonNumericSensor(HonBaseEntity, SensorEntity):
    """Sensore generico numerico per un attributo di un appliance hOn."""

    def __init__(
        self,
        coordinator,
        appliance_id: str,
        attr_key: str,
        name: str,
        unique_suffix: str,
        unit: str | None,
        device_class,
        state_class,
    ) -> None:
        super().__init__(coordinator, appliance_id)
        device_name = self.coordinator.data.get(appliance_id, {}).get("name", "Haier")
        self._attr_name = f"{device_name} - {name}"
        self._attr_unique_id = f"{appliance_id}_{unique_suffix}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_key = attr_key

    @property
    def native_value(self):
        val = self._get_attr(self._attr_key)
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None


class HonWMStateSensor(HonBaseEntity, SensorEntity):
    """Sensore stato lavatrice (testo leggibile)."""

    def __init__(self, coordinator, appliance_id: str) -> None:
        super().__init__(coordinator, appliance_id)
        device_name = self.coordinator.data.get(appliance_id, {}).get("name", "Lavatrice")
        self._attr_name = f"{device_name} - Stato"
        self._attr_unique_id = f"{appliance_id}_state"
        self._attr_icon = "mdi:washing-machine"

    @property
    def native_value(self) -> str | None:
        val = self._get_attr(WM_ATTR_STATUS)
        if val is None:
            return None
        return WM_STATE_MAP.get(str(val), f"Stato {val}")
