# Changelog - v2.0.3

## 🔴 CRITICAL FIXES

### hon_client.py
- **Rimosso duplicato `run_command_sync()`** (riga ~175-180)
  - La funzione era definita due volte, la seconda sovrascriveva la prima
  - Mantenuta una sola definizione chiara e funzionante

---

## 🟠 MAJOR FIXES

### climate.py
- **Semplificato HVACMode enum handling** (righe 83-94)
  - ❌ `mode_str = hvac_mode.value if hasattr(hvac_mode, "value") else str(hvac_mode)`
  - ✅ `mode_str = hvac_mode.value` (HVACMode è StrEnum, .value basta)
  - Rimosso `.lower()` ridondante

- **Usate costanti da const.py per coerenza** (righe 42, 55)
  - ❌ `self._get_attr("machMode", "1")` → ✅ `self._get_attr(AC_ATTR_MODE, "1")`
  - ❌ `self._get_attr("tempSel")` → ✅ `self._get_attr(AC_ATTR_TEMP)`
  - ❌ `self._get_attr("onOffStatus", "0")` → ✅ `self._get_attr(AC_ATTR_ON_OFF, "0")`
  - ❌ `self._get_attr("windSpeed", "0")` → ✅ `self._get_attr(AC_ATTR_FAN_SPEED, "0")`
  - Aggiunto import di tutte le costanti necessarie

- **Fixed fallback target_temperature**
  - ❌ `return 24.0 if val is None` (menzogna al frontend)
  - ✅ `return None` (dato non disponibile)
  - Ora coerente con `current_temperature` che ritorna None

---

## 🟡 MINOR FIXES

### select.py
- **Fixed falsy check su programma 0** (righe 65-71)
  - ❌ `code = (self._get_attr(...) or self._get_attr(...) or ...)` 
    - Scarta il valore 0 come falsy
  - ✅ Loop esplicito con check `is not None`
    - Accetta correttamente il programma 0 (Cotone)

### manifest.json
- **Aggiornato numero versione** da 2.0.2.1 → 2.0.3 (release delle fix)

---

## 📋 SUMMARY

| File | Tipo Fix | Numero Cambi |
|------|----------|-------------|
| hon_client.py | CRITICAL | 1 |
| climate.py | MAJOR | 4 |
| select.py | MINOR | 1 |
| manifest.json | VERSION | 1 |

**Totale:** 8 fix applicati

---

## 🧪 Testing Recommendation

Dopo il deploy, verificare:
1. ✅ Climate entity: cambio modalità (OFF/COOL/HEAT/etc.)
2. ✅ Climate entity: lettura temperatura corretta (non 24.0 di default)
3. ✅ Select entity: selezione programma 0 (Cotone)
4. ✅ Sensori: umidità interna registrata correttamente

---

## 📝 Note Tecniche

- **HVACMode**: Home Assistant usa StrEnum, quindi `.value` torna direttamente la stringa ("cool", "heat", ecc.)
- **Fallback temperature**: Ritornare un valore fittizio è peggio che ritornare None — il frontend vede None come "dato in caricamento"
- **Falsy check in Python**: `or` scarta 0, "", False — usare `is not None` per valori che possono essere 0

---

## 🔗 Git Info

- **Versione precedente:** 2.0.2.1 (con bug)
- **Versione corrente:** 2.0.3 (fix applicati)
- **Branch:** main
- **Compatibility:** pyhOn >= 0.17.5

