"""Diagnostics support for Haier hOn (Extended)."""
from __future__ import annotations

from collections.abc import Mapping

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


def _redact_email(email: str | None) -> str | None:
    if not email:
        return None
    if "@" in email:
        _, domain = email.split("@", 1)
        return f"***@{domain}"
    return "***"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    domain_data = hass.data.get(DOMAIN, {})
    entry_data = domain_data.get(entry.entry_id, {})
    coordinator = entry_data.get("coordinator")

    appliances: list[dict] = []
    coord_data = getattr(coordinator, "data", None)
    if isinstance(coord_data, dict):
        for appliance_id, data in coord_data.items():
            appliance = data.get("appliance")
            commands_info: dict[str, list[str]] = {}

            commands = getattr(appliance, "commands", None)
            if isinstance(commands, Mapping):
                for cmd_name, cmd in commands.items():
                    params = getattr(cmd, "parameters", None)
                    if isinstance(params, Mapping):
                        commands_info[cmd_name] = sorted([str(k) for k in params.keys()])
                    else:
                        commands_info[cmd_name] = []

            attributes = data.get("attributes") if isinstance(data, dict) else None
            settings = data.get("settings") if isinstance(data, dict) else None

            appliances.append(
                {
                    "id": "***",
                    "name": data.get("name"),
                    "type": data.get("type"),
                    "model": data.get("model"),
                    "serial": "***",
                    "attribute_keys": sorted(list(attributes.keys()))
                    if isinstance(attributes, dict)
                    else [],
                    "settings_keys": sorted(list(settings.keys()))
                    if isinstance(settings, dict)
                    else [],
                    "commands": commands_info,
                }
            )

    return {
        "entry": {
            "title": entry.title,
            "data": {
                "email": _redact_email(entry.data.get("email")),
                "password": "***",
            },
            "options": dict(entry.options),
        },
        "appliances": appliances,
    }

