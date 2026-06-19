"""OV (oven). Rewrite of pyhOn's `appliances/ov.py`.

Offline zeroing of temp/onOffStatus/remoteCtrValid/remainingTimeMM; `active` =
onOffStatus==1. ON PAR with pyhOn (it already used `.value == 1`, correct). Robustness:
`.get`/no-op on absent keys instead of pyhOn's KeyError.
"""
from __future__ import annotations

from typing import Any

from .base import ApplianceExtra


class Appliance(ApplianceExtra):
    def attributes(self, data: dict[str, Any]) -> dict[str, Any]:
        data = super().attributes(data)
        params = data.get("parameters", {})
        # no offline zeroing: availability via `available` (see td.py/base_entity).
        data["active"] = self._is_value(params, "onOffStatus", 1)
        return data
