"""REF (refrigerator). Rewrite of pyhOn's `appliances/ref.py`.

modeZ1/modeZ2 from the holiday/intelligence/quickMode flags. FIX vs pyhOn: the comparison
is by VALUE (pyhOn did `HonAttribute == "1"` = always False -> modeZ1/Z2 were always
`no_mode`). Fields NOT consumed by the integration (the real modes are computed by the
Tier-0 mapping from the shadow) -> the fix is inert but correct.

Documented app divergence (see apk/analysis/per-type-derivations.md #3): the app inverts
the Z1 priority (super_cool BEFORE holiday) and has an `energySavingStatus`~auto_set alias.
We keep pyhOn's order (the modes are mutually exclusive via startProgram/stopProgram,
the inversion is cosmetic) until we validate live on the AC/fridge.
"""
from __future__ import annotations

from typing import Any

from .base import ApplianceExtra


class Appliance(ApplianceExtra):
    def attributes(self, data: dict[str, Any]) -> dict[str, Any]:
        data = super().attributes(data)
        params = data.get("parameters", {})
        if self._is_value(params, "holidayMode", 1):
            data["modeZ1"] = "holiday"
        elif self._is_value(params, "intelligenceMode", 1):
            data["modeZ1"] = "auto_set"
        elif self._is_value(params, "quickModeZ1", 1):
            data["modeZ1"] = "super_cool"
        else:
            data["modeZ1"] = "no_mode"

        if self._is_value(params, "quickModeZ2", 1):
            data["modeZ2"] = "super_freeze"
        elif self._is_value(params, "intelligenceMode", 1):
            data["modeZ2"] = "auto_set"
        else:
            data["modeZ2"] = "no_mode"
        return data
