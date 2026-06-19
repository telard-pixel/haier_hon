"""TD (tumble dryer). Rewrite of pyhOn's `appliances/td.py`.

`active`/offline-zeroing on par with pyhOn (they worked). `pause` FIX: by value
(pyhOn `machMode == "3"` = always False; field not consumed, inert but correct fix).
`settings`: hides `startProgram.dryLevel` when it is an "unselected" fixed value.
App IMPROVEMENT (per-type-derivations.md #4): the app hides it for '11' AND '0'/empty
(pyhOn only '11'); our fixed `value` is never "" (getter -> "0"), hence {"0","11"}.
"""
from __future__ import annotations

from typing import Any

from ..parameter.fixed import HonParameterFixed
from .base import ApplianceExtra

_DRY_HIDDEN = {"", "0", "11"}


class Appliance(ApplianceExtra):
    def attributes(self, data: dict[str, Any]) -> dict[str, Any]:
        data = super().attributes(data)
        params = data.get("parameters", {})
        # no offline zeroing: availability is handled via `available`
        # (HA entity -> unavailable if disconnected), as the app does (it keeps the last
        # values and signals connectivity). See base_entity.available.
        data["active"] = bool(data.get("activity"))
        data["pause"] = self._is_value(params, "machMode", 3)
        return data

    def settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        dry_level = settings.get("startProgram.dryLevel")
        if isinstance(dry_level, HonParameterFixed) and str(dry_level.value) in _DRY_HIDDEN:
            settings.pop("startProgram.dryLevel", None)
        return settings
