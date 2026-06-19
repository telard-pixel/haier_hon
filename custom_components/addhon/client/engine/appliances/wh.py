"""WH (water heater). Rewrite of pyhOn's `appliances/wh.py`.

`active` = onOffStatus==1. FIX vs pyhOn: pyhOn did `isinstance(attr, HonParameter)`
(false: it is a HonAttribute) -> the `attr == 1` branch = always False -> active broken. Here by
value (correct). Field not consumed -> inert but correct fix.
"""
from __future__ import annotations

from typing import Any

from .base import ApplianceExtra


class Appliance(ApplianceExtra):
    def attributes(self, data: dict[str, Any]) -> dict[str, Any]:
        data = super().attributes(data)
        data["active"] = self._is_value(data.get("parameters", {}), "onOffStatus", 1)
        return data
