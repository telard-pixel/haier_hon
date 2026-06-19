"""DW (dishwasher). Rewrite of pyhOn's `appliances/dw.py`.

`active = bool(activity)`, offline machMode zeroing. No `pause` (like pyhOn).
"""
from __future__ import annotations

from typing import Any

from .base import ApplianceExtra


class Appliance(ApplianceExtra):
    def attributes(self, data: dict[str, Any]) -> dict[str, Any]:
        data = super().attributes(data)
        # no offline zeroing: availability via `available` (see td.py/base_entity).
        data["active"] = bool(data.get("activity"))
        return data
