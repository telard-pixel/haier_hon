"""HonParameterEnum nativo, con il FIX del bug BABYCARE.

Porting di `_vendor/pyhon/parameter/enum.py`. UNICA divergenza voluta: il setter.
pyhOn confronta il valore GREZZO in ingresso contro `self.values` che è GIA'
normalizzato da `clean_value` (lowercase, strip `[]`, `|`->`_`). Così un valore con
casing del cloud (es. "BABYCARE") non combacia mai con ["babycare"] -> ValueError.
È il bug BABYCARE, qui FIXATO alla radice (il vecchio monkeypatch su pyhOn non esiste
più).

Il setter normalizza il valore in ingresso con lo
STESSO `clean_value` prima del confronto. Accetta sia "BABYCARE" sia "babycare";
memorizza il valore grezzo (così `intern_value` resta grezzo = ciò che si invia al
cloud). Sul caso reale (valori già puliti del frigo) e sulla superficie che
l'integrazione usa davvero (imposta valori presi da `param.values`, già puliti) il
comportamento è IDENTICO a pyhOn+patch: lo verifica il differential test su 67
parametri reali.

DIVERGENZE VOLUTE da pyhOn+patch su valori-edge (cased/`|`/`[]`), tutte = native
PIÙ CORRETTO (il patch era un bolt-on incoerente), da rivalidare LIVE sull'AC
(l'oracolo vero lì è l'app, non pyhOn, vedi FASE4 plan):
  1. TRIGGER: native chiama `check_trigger` su OGNI valore accettato (come il ramo
     normale di pyhOn); il fallback del patch impostava `_value` ma DIMENTICAVA il
     trigger -> su valori col casing del cloud le rules non cascatavano. Native le fa
     cascadere coerentemente (corretto).
  2. ACCETTAZIONE: native accetta un valore se la sua forma normalizzata è tra i
     valori ammessi (regola unica e coerente); il patch accettava solo match esatti
     grezzi o puliti. L'integrazione imposta sempre forme pulite da `param.values`,
     quindi in pratica non cambia.
  3. `|`-STRING: con `enumValues` come STRINGA "A|B|C" il patch accettava per un
     QUIRK di substring (`"A|B|C" in "A|B|C"`); native no. Caso degenere; lo split `|`
     corretto è gestito a monte (l'app lo splitta).
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
        # `enumValues` di norma e' una lista; alcuni payload la danno come stringa
        # "A|B|C". Normalizza a lista cosi' .append/.values non si rompono (prima una
        # stringa qui causava AttributeError in __init__ o un'iterazione carattere-per-
        # carattere). Lo split "|" e' coerente con _apply_enum (rules.py).
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
        # FIX BABYCARE: confronto sul valore NORMALIZZATO (pyhOn confrontava il grezzo
        # contro la lista già pulita -> falso negativo sui valori col casing del cloud).
        if clean_value(value) in self.values:
            self._value = value
            self.check_trigger(value)
        else:
            raise ValueError(f"Allowed values: {self._values} But was: {value}")
