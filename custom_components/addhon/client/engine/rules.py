"""Motore rules nativo. Porting di `_vendor/pyhon/rules.py`.

Una "rule" lega un parametro-trigger a un'azione su un altro parametro: quando il
trigger assume un certo valore, il target viene vincolato (valore fisso, oppure
ristretto a un enum/range). Si aggancia via `parameter.add_trigger` (il sistema di
trigger del parametro base nativo): quando il trigger cambia valore, `check_trigger`
esegue le callback registrate qui.

MODELLO rules — RISOLTO sull'AC live (2026-06-18, vedi apk/analysis/rules-model.md):
  Il vecchio dubbio "pyhОn forse trasposto vs il modello `programRules` dell'app" era un
  MISREADING. Dump dell'AC reale (apk/dump/ac_live): `ancillaryParameters.programRules` È
  il parametro con `category=="rule"`, stesso nodo, stesso nesting
  `{targetParam: {triggerParam: {triggerValue: action}}}` (+ condizioni-extra annidate
  es. `tempSel: {ecoMode: {"1": {machMode: {"1": {fixedValue:"26"}}}}}`). Quindi il
  modello di pyhОn = il modello dell'app: già allineati, niente da "adottare".
  UNA divergenza VOLUTA dopo la validazione live: il fix di `_extra_rules_matches`
  (vedi sotto) - pyhОn confrontava `str(param)` (repr) invece di `str(param.value)`,
  quindi le condizioni-extra non scattavano MAI; sull'AC reale ecoMode=1 ora vincola
  tempSel/windSpeed/windDirection come fa l'app.
  NOTA: le rules con trigger `$installationType` (config statica multi-split, non un
  parametro) NON scattano (come in pyhОn: `$` non strippato, options vuote a
  costruzione); impatto basso (remoteVisible/selfClean), non implementato alla cieca.

`isinstance` qui è contro le classi parametro NATIVE: parametri, comandi e rules sono
un cluster coeso.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .parameter.base import HonParameter
from .parameter.enum import HonParameterEnum
from .parameter.range import HonParameterRange


@dataclass
class HonRule:
    trigger_key: str
    trigger_value: str
    param_key: str
    param_data: dict[str, Any]
    extras: Optional[dict[str, str]] = None


# Trigger key `$<x>` = variabile di CONFIG del device (sigil dell'app), non un
# parametro runtime. Mappatura -> campo del record appliance (da app decompilata,
# `getMappedParamName`): l'app conosce SOLO `$installationType` -> `unitConfiguration`.
_DOLLAR_FIELDS = {"$installationType": "unitConfiguration"}


class HonRuleSet:
    def __init__(self, command: Any, rule: dict[str, Any]) -> None:
        self._command = command
        self._rules: dict[str, list[HonRule]] = {}
        # rules "di config" (trigger `$...`): risolte staticamente, non via trigger.
        self._config_rules: list[tuple[str, str, dict[str, Any]]] = []
        self._parse_rule(rule)

    @property
    def rules(self) -> dict[str, list[HonRule]]:
        return self._rules

    def _parse_rule(self, rule: dict[str, Any]) -> None:
        for param_key, params in rule.items():
            param_key = self._command.appliance.options.get(param_key, param_key)
            for trigger_key, trigger_data in params.items():
                self._parse_conditions(param_key, trigger_key, trigger_data)

    def _parse_conditions(
        self,
        param_key: str,
        trigger_key: str,
        trigger_data: dict[str, Any],
        extra: Optional[dict[str, str]] = None,
    ) -> None:
        if extra is None and trigger_key.startswith("$"):
            # CONFIG-rule (modello app): il trigger `$installationType` non è un
            # parametro ma un campo del device (unitConfiguration). Risolta staticamente
            # in `patch()` contro il record appliance, non come trigger runtime.
            self._config_rules.append((param_key, trigger_key, trigger_data))
            return
        trigger_key = trigger_key.replace("@", "")
        trigger_key = self._command.appliance.options.get(trigger_key, trigger_key)
        for multi_trigger_value, param_data in trigger_data.items():
            for trigger_value in multi_trigger_value.split("|"):
                if isinstance(param_data, dict) and "typology" in param_data:
                    self._create_rule(
                        param_key, trigger_key, trigger_value, param_data, extra
                    )
                elif isinstance(param_data, dict):
                    # Copia per ramo: `extra` non va mutato/condiviso tra le iterazioni
                    # del loop, altrimenti una rule gia' creata in un ramo precedente
                    # vedrebbe la condizione di un ramo successivo (es. ecoMode 1 -> 2).
                    branch_extra = dict(extra or {})
                    branch_extra[trigger_key] = trigger_value
                    for extra_key, extra_data in param_data.items():
                        self._parse_conditions(
                            param_key, extra_key, extra_data, branch_extra
                        )
                else:
                    param_data = {"typology": "fixed", "fixedValue": param_data}
                    self._create_rule(
                        param_key, trigger_key, trigger_value, param_data, extra
                    )

    def _create_rule(
        self,
        param_key: str,
        trigger_key: str,
        trigger_value: str,
        param_data: dict[str, Any],
        extras: Optional[dict[str, str]] = None,
    ) -> None:
        if param_data.get("fixedValue") == f"@{param_key}":
            return
        self._rules.setdefault(trigger_key, []).append(
            HonRule(
                trigger_key,
                trigger_value,
                param_key,
                param_data,
                extras.copy() if extras is not None else None,
            )
        )

    def _duplicate_for_extra_conditions(self) -> None:
        new: dict[str, list[HonRule]] = {}
        for rules in self._rules.values():
            for rule in rules:
                if rule.extras is None:
                    continue
                for key, value in rule.extras.items():
                    extras = rule.extras.copy()
                    extras.pop(key)
                    extras[rule.trigger_key] = rule.trigger_value
                    new.setdefault(key, []).append(
                        HonRule(key, value, rule.param_key, rule.param_data, extras)
                    )
        for key, rules in new.items():
            for rule in rules:
                self._rules.setdefault(key, []).append(rule)

    def _extra_rules_matches(self, rule: HonRule) -> bool:
        if rule.extras:
            for key, value in rule.extras.items():
                param = self._command.parameters.get(key)
                if not param:
                    return False
                # FIX (validato sull'AC live, 2026-06-18): confronta il VALORE del
                # parametro, non l'oggetto. pyhОn faceva `str(param)` (= il repr
                # dell'oggetto) != `str(value)`, SEMPRE vero -> le condizioni-extra
                # (rules annidate, es. AC `ecoMode==1 AND machMode==1 -> tempSel=26`)
                # non scattavano MAI. Qui confrontiamo `str(param.value)`: sull'AC reale
                # ecoMode=1 ora vincola correttamente tempSel/windSpeed/windDirection
                # come fa l'app. Divergenza voluta vs pyhОn (suo bug).
                if str(param.value) != str(value):
                    return False
        return True

    def _apply_fixed(self, param: HonParameter, value: str | float) -> None:
        if isinstance(param, HonParameterEnum) and set(param.values) != {str(value)}:
            param.values = [str(value)]
            param.value = str(value)
        elif isinstance(param, HonParameterRange):
            numeric = float(value)
            if numeric < param.min:
                param.min = numeric
            elif numeric > param.max:
                param.max = numeric
            # Passa una STRINGA al setter: str_to_float fa int() per primo e un float
            # come 22.5 verrebbe troncato a 22 (vedi helpers.str_to_float). La stringa
            # preserva i decimali (stesso motivo per cui number.py invia i setpoint come str).
            param.value = str(value)
            return
        param.value = str(value)

    def _apply_enum(self, param: HonParameter, rule: HonRule) -> None:
        if not isinstance(param, HonParameterEnum):
            return
        if enum_values := rule.param_data.get("enumValues"):
            param.values = enum_values.split("|")
        if default_value := rule.param_data.get("defaultValue"):
            # NB enum-casing: se `defaultValue` ha un casing diverso
            # dai suoi `enumValues`, il nostro setter lo accetta (fix BABYCARE) mentre
            # pyhОn+patch solleverebbe (e il chiamante del trigger inghiotte l'errore).
            # Caso degenere, non validabile offline -> rimandato a live-AC.
            param.value = default_value

    def _add_trigger(self, parameter: HonParameter, data: HonRule) -> None:
        def apply(rule: HonRule) -> None:
            if not self._extra_rules_matches(rule):
                return
            if not (param := self._command.parameters.get(rule.param_key)):
                return
            if fixed_value := rule.param_data.get("fixedValue", ""):
                self._apply_fixed(param, fixed_value)
            elif rule.param_data.get("typology") == "enum":
                self._apply_enum(param, rule)

        parameter.add_trigger(data.trigger_value, apply, data)

    def _apply_config_rules(self) -> None:
        """Applica le rules con trigger `$...` (config statica del device) come fa l'app:
        risolve il campo del record appliance (es. `$installationType`->`unitConfiguration`),
        indicizza il ramo col valore del device e ne scrive il `fixedValue`/enum nel target.
        Statico (il valore è una proprietà persistente del device, non cambia operando).
        Se il device non ha quel campo o non c'è un ramo per il suo valore -> non scatta
        (come l'app: `if(!r5) return`). Validato live: AC `unitConfiguration='1to1'` -> nessun
        ramo (le rules hanno solo 1to2/1toN) -> non scatta, corretto."""
        if not self._config_rules:
            return
        info = getattr(self._command.appliance, "info", {}) or {}
        for param_key, dollar_key, branch_map in self._config_rules:
            field = _DOLLAR_FIELDS.get(dollar_key, dollar_key)
            device_value = info.get(field)
            if device_value is None:
                continue
            action = branch_map.get(str(device_value))
            if not isinstance(action, dict):
                continue
            if not (param := self._command.parameters.get(param_key)):
                continue
            if fixed_value := action.get("fixedValue", ""):
                self._apply_fixed(param, fixed_value)
            elif action.get("typology") == "enum":
                self._apply_enum(
                    param, HonRule(dollar_key, str(device_value), param_key, action)
                )

    def patch(self) -> None:
        self._duplicate_for_extra_conditions()
        for name, parameter in self._command.parameters.items():
            if name not in self._rules:
                continue
            for data in self._rules.get(name, []):
                self._add_trigger(parameter, data)
        self._apply_config_rules()
