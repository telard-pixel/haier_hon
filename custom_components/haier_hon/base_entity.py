"""Entità base per Haier hOn."""
from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class HonBaseEntity(CoordinatorEntity):
    """Entità base per tutti i dispositivi Haier hOn."""

    def __init__(self, coordinator, appliance_id: str) -> None:
        super().__init__(coordinator)
        self._appliance_id = appliance_id

    @property
    def _hon_client(self):
        """Ritorna il HonClient per eseguire comandi sul loop dedicato."""
        from homeassistant.core import HomeAssistant  # noqa: F401
        ha_data = self.hass.data.get(DOMAIN, {})
        for entry_data in ha_data.values():
            if isinstance(entry_data, dict) and "client" in entry_data:
                return entry_data["client"]
        return None

    @property
    def _appliance_data(self) -> dict:
        return self.coordinator.data.get(self._appliance_id, {})

    @property
    def _attributes(self) -> dict:
        return self._appliance_data.get("attributes", {})

    @property
    def _appliance(self):
        return self._appliance_data.get("appliance")

    @property
    def device_info(self) -> DeviceInfo:
        data = self._appliance_data
        return DeviceInfo(
            identifiers={(DOMAIN, self._appliance_id)},
            name=data.get("name", "Haier Appliance"),
            manufacturer="Haier",
            model=data.get("model", "Unknown"),
            sw_version=None,
        )

    def _get_attr(self, key: str, default=None):
        """Recupera un attributo del dispositivo.
        
        pyhOn restituisce gli attributi come HonAttribute (con .value)
        oppure come valori raw a seconda della versione. Gestiamo entrambi.
        """
        def _extract_value(value):
            if value is None:
                return None
            # HonAttribute ha .value — nota: value.value può essere 0, "", False (tutti validi!)
            if hasattr(value, "value"):
                inner = value.value
                # Stringa vuota = dato non disponibile, trattala come None
                if inner == "":
                    return None
                return inner
            # Stringa vuota raw = dato non disponibile
            if value == "":
                return None
            return value

        def _deep_get(container, path: str):
            current = container
            for part in path.split("."):
                if current is None:
                    return None
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    current = getattr(current, part, None)
            return current

        # 1) lookup diretto (chiavi già "flattened")
        val = self._attributes.get(key)
        if val is not None:
            return _extract_value(val)

        # 2) supporto prefisso "settings." (alcuni modelli/vecchie versioni lo usano)
        if key.startswith("settings."):
            key_no_prefix = key.removeprefix("settings.")
            val = self._attributes.get(key_no_prefix)
            if val is not None:
                return _extract_value(val)

            val = _deep_get(self._attributes, key_no_prefix)
            if val is not None:
                return _extract_value(val)

            settings = self._appliance_data.get("settings")
            if isinstance(settings, dict):
                val = settings.get(key_no_prefix)
                if val is not None:
                    return _extract_value(val)
                val = _deep_get(settings, key_no_prefix)
                if val is not None:
                    return _extract_value(val)

        # 2b) supporto prefisso "startProgram." (es. ecoMode che vive in startProgram)
        if key.startswith("startProgram."):
            key_no_prefix = key.removeprefix("startProgram.")
            val = self._attributes.get(key_no_prefix)
            if val is not None:
                return _extract_value(val)

            start_program = self._appliance_data.get("startProgram")
            if isinstance(start_program, dict):
                val = start_program.get(key_no_prefix)
                if val is not None:
                    return _extract_value(val)
                val = _deep_get(start_program, key_no_prefix)
                if val is not None:
                    return _extract_value(val)

        # 3) fallback: prova lookup "dotted path" dentro attributes
        val = _deep_get(self._attributes, key)
        if val is not None:
            return _extract_value(val)

        return default
