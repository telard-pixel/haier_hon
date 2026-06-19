"""Native base ApplianceExtra. Rewrite of pyhOn's `appliances/base.py`.

Per-type hooks on the appliance state:
- `attributes(data)`: post-processes the shadow (adds derived fields).
- `settings(result)`: tweaks the settings dict (default: no-op).

`parent` is the appliance (duck-typed): it needs `.settings`, `.connection`.
The VALUES in `data["parameters"][...]` are `HonAttribute`s (native): we read them
duck-typed via `.value`/`str()`. The `isinstance` checks instead are against the
native PARAMETER classes.

Comparison helper: pyhOn compared `HonAttribute == "1"`, which is ALWAYS False
(no `__eq__`) -> ref/td/wm pause were broken no-ops. Here we compare by VALUE
(the app's intent), fixing the bug. The fields that depend on it (modeZ1/Z2/pause) are
however not consumed by the integration: the difference is documented, not risky.
"""
from __future__ import annotations

from typing import Any

from ..parameter.program import HonParameterProgram


class ApplianceExtra:
    def __init__(self, appliance: Any) -> None:
        self.parent = appliance

    # --- attribute-reading helpers (duck-typed on HonAttribute) ---
    @staticmethod
    def _raw(params: dict[str, Any], key: str) -> str:
        """Raw value (string) via __str__. ONLY for fields never set to a number
        (e.g. prCode): after a numeric set __str__ would raise. For flags use _value."""
        if key not in params:
            return ""
        return str(params[key])

    @staticmethod
    def _value(params: dict[str, Any], key: str, default: Any = None) -> Any:
        """Typed attribute value (`.value`, numeric if convertible),
        default if absent."""
        attr = params.get(key)
        return attr.value if attr is not None and hasattr(attr, "value") else default

    @classmethod
    def _is_value(cls, params: dict[str, Any], key: str, expected: Any) -> bool:
        """True if the `key` attribute's `.value` == expected. Comparison by VALUE
        (flags "1"/"0" become int 1/0): replaces pyhOn's `HonAttribute == "..."`,
        which is ALWAYS False (no __eq__) -> its modeZ/pause were no-ops."""
        return cls._value(params, key) == expected

    def attributes(self, data: dict[str, Any]) -> dict[str, Any]:
        # programName: slug from the current program code (like pyhOn; the app uses an
        # i18n key resolved via dictionaryId = wrong altitude for HA).
        # Robustness vs pyhOn: `_raw(...) or "0"` handles an empty/absent prCode -> "No
        # Program" instead of pyhOn's `int("")` -> ValueError (intentional divergence, safe).
        program_name = "No Program"
        params = data.get("parameters", {})
        if program := int(self._raw(params, "prCode") or "0"):
            start_cmd = self.parent.settings.get("startProgram.program")
            if isinstance(start_cmd, HonParameterProgram) and (ids := start_cmd.ids):
                program_name = ids.get(program, program_name)
        data["programName"] = program_name
        # available: connectivity as a first-class attribute (app model). Offline
        # is handled by entity availability (base_entity), no longer by zeroing
        # the parameters. (See apk/analysis/per-type-derivations.md #5.)
        data["available"] = bool(self.parent.connection)
        return data

    def settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        return settings
