"""Native per-type registry.

Replaces pyhOn's dynamic `importlib.import_module(f"...appliances.{type}")` with
a STATIC type->class map: no runtime import, explicit dependencies, and the IDE/
linter sees the references. Selection follows pyhOn: key = `appliance_type.lower()`;
a type without a per-type class -> no extra (like pyhOn's ModuleNotFoundError).
"""
from __future__ import annotations

from typing import Any, Optional, Type

from . import dw, ov, ref, td, wc, wd, wh, wm
from .base import ApplianceExtra

# key = appliance_type.lower() (the same types pyhOn had in appliances/*.py)
_REGISTRY: dict[str, Type[ApplianceExtra]] = {
    "dw": dw.Appliance,
    "ov": ov.Appliance,
    "ref": ref.Appliance,
    "td": td.Appliance,
    "wc": wc.Appliance,
    "wd": wd.Appliance,
    "wh": wh.Appliance,
    "wm": wm.Appliance,
}


def get_extra(appliance: Any) -> Optional[ApplianceExtra]:
    """Instantiate the appliance's per-type extra, or None if the type has none
    (like pyhOn when the per-type module does not exist)."""
    cls = _REGISTRY.get(str(appliance.appliance_type).lower())
    return cls(appliance) if cls is not None else None
