"""Native HonParameterEnum, with the BABYCARE bug FIX.

Porting of `_vendor/pyhon/parameter/enum.py`. The ONLY intentional divergence: the setter.
pyhOn compares the RAW incoming value against `self.values`, which is ALREADY
normalized by `clean_value` (lowercase, strip `[]`, `|`->`_`). So a value with
the cloud's casing (e.g. "BABYCARE") never matches ["babycare"] -> ValueError.
That is the BABYCARE bug, FIXED here at the root (the old pyhOn monkeypatch no longer
exists).

The setter normalizes the incoming value with the
SAME `clean_value` before comparing. It accepts both "BABYCARE" and "babycare";
it stores the raw value (so `intern_value` stays raw = what gets sent to the
cloud). On the real case (the fridge's already-clean values) and on the surface the
integration actually uses (it sets values taken from `param.values`, already clean) the
behavior is IDENTICAL to pyhOn+patch: the differential test verifies it on 67
real parameters.

INTENTIONAL DIVERGENCES from pyhOn+patch on edge values (cased/`|`/`[]`), all = native
MORE CORRECT (the patch was an inconsistent bolt-on), to re-validate LIVE on the AC
(the true oracle there is the app, not pyhOn, see the FASE4 plan):
  1. TRIGGER: native calls `check_trigger` on EVERY accepted value (like pyhOn's
     normal branch); the patch's fallback set `_value` but FORGOT the
     trigger -> on cloud-cased values the rules did not cascade. Native cascades them
     consistently (correct).
  2. ACCEPTANCE: native accepts a value if its normalized form is among the
     allowed values (a single, consistent rule); the patch accepted only exact raw
     or clean matches. The integration always sets clean forms from `param.values`,
     so in practice it does not change.
  3. `|`-STRING: with `enumValues` as a STRING "A|B|C" the patch accepted it due to a
     substring QUIRK (`"A|B|C" in "A|B|C"`); native does not. Degenerate case; the
     correct `|` split is handled upstream (the app splits it).
"""
from __future__ import annotations

from typing import Any

from .base import HonParameter


def clean_value(value: str | float) -> str:
    return str(value).strip("[]").replace("|", "_").lower()


class HonParameterEnum(HonParameter):
    def __init__(self, key: str, attributes: dict[str, Any], group: str) -> None:
        super().__init__(key, attributes, group)
        self._default: str | float = ""
        self._value: str | float = ""
        self._values: list[str] = []
        self._set_attributes()
        if self._default and clean_value(self._default) not in self.values:
            self._values.append(str(self._default))

    def _set_attributes(self) -> None:
        super()._set_attributes()
        self._default = self._attributes.get("defaultValue", "")
        self._value = self._default or "0"
        # `enumValues` is normally a list; some payloads give it as the string
        # "A|B|C". Normalize to a list so .append/.values do not break (before, a
        # string here caused an AttributeError in __init__ or a character-by-character
        # iteration). The "|" split is consistent with _apply_enum (rules.py).
        raw_values = self._attributes.get("enumValues", [])
        if isinstance(raw_values, str):
            self._values = raw_values.split("|")
        elif isinstance(raw_values, list):
            self._values = [str(v) for v in raw_values]
        else:
            self._values = []

    def __repr__(self) -> str:
        return f"{self.__class__} (<{self.key}> {self.values})"

    @property
    def values(self) -> list[str]:
        return [clean_value(value) for value in self._values]

    @values.setter
    def values(self, values: list[str]) -> None:
        self._values = values

    @property
    def intern_value(self) -> str:
        return str(self._value) if self._value is not None else str(self.values[0])

    @property
    def value(self) -> str | float:
        return clean_value(self._value) if self._value is not None else self.values[0]

    @value.setter
    def value(self, value: str | float) -> None:
        # BABYCARE FIX: compare on the NORMALIZED value (pyhOn compared the raw one
        # against the already-clean list -> false negative on cloud-cased values).
        if clean_value(value) in self.values:
            self._value = value
            self.check_trigger(value)
        else:
            raise ValueError(f"Allowed values: {self._values} But was: {value}")
