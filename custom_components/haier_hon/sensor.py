"""Sensori per Haier hOn - temperature, compressore, lavatrice."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import UnitOfEnergy, UnitOfVolume, UnitOfTime, UnitOfTemperature

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
            entities.extend([
                HonNumericSensor(coordinator, appliance_id, AC_ATTR_CURRENT_TEMP, "Temperatura Interna", "temp_indoor", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
                HonNumericSensor(coordinator, appliance_id, AC_ATTR_OUTDOOR_TEMP, "Temperatura Esterna", "temp_outdoor", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
                HonNumericSensor(coordinator, appliance_id, AC_ATTR_HUMIDITY_INDOOR, "Umidità Interna", "humidity_indoor", "%", SensorDeviceClass.HUMIDITY, SensorStateClass.MEASUREMENT),
                HonNumericSensor(coordinator, appliance_id, AC_ATTR_COMPRESSOR_FREQ, "Frequenza Compressore", "compressor_freq", "Hz", None, SensorStateClass.MEASUREMENT),
                HonNumericSensor(coordinator, appliance_id, AC_ATTR_TOTAL_ENERGY, "Energia Totale Condizionatore", "total_energy", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
            ])

        elif app_type in APPLIANCE_WASH_GROUP:
            entities.extend([
                HonWMStateSensor(coordinator, appliance_id),
                HonNumericSensor(coordinator, appliance_id, WM_ATTR_REMAINING, "Tempo Rimanente", "remaining_time", UnitOfTime.MINUTES, SensorDeviceClass.DURATION, None),
                HonNumericSensor(coordinator, appliance_id, WM_ATTR_TOTAL_WASH, "Cicli Totali", "total_washes", None, None, SensorStateClass.TOTAL_INCREASING),
                HonNumericSensor(coordinator, appliance_id, WM_ATTR_TOTAL_WATER, "Acqua Totale Consumata", "total_water", UnitOfVolume.LITERS, SensorDeviceClass.WATER, SensorStateClass.TOTAL_INCREASING),
                HonNumericSensor(coordinator, appliance_id, WM_ATTR_TOTAL_ENERGY, "Energia Totale Consumata", "total_energy", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
                HonNumericSensor(coordinator, appliance_id, WM_ATTR_CURRENT_ENERGY, "Consumo Energetico Attuale", "current_energy", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
                HonNumericSensor(coordinator, appliance_id, WM_ATTR_CURRENT_WATER, "Consumo Acqua Attuale", "current_water", UnitOfVolume.LITERS, SensorDeviceClass.WATER, SensorStateClass.TOTAL),
            ])

    async_add_entities(entities)


class HonNumericSensor(HonBaseEntity, SensorEntity):
    """Sensore generico per attributi numerici (compatibile con statistiche HA)."""

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
    def native_value(self) -> str:
        status_code = str(self._get_attr(WM_ATTR_STATUS))
        return WM_STATE_MAP.get(status_code, f"Sconosciuto ({status_code})")