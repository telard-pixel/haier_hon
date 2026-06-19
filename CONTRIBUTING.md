# Contributing to addhOn

## Language policy

This project separates **code** from **interface**:

- **Code is English-only.** All source code, comments, docstrings, log messages,
  and internal/log-only error strings must be in English and ASCII. The end user
  never reads the code, so it stays in one language. This is enforced by
  `tests/test_code_is_english.py`, which fails on any non-ASCII character in
  `custom_components/addhon/**/*.py` (a tiny allow-list covers scientific unit
  symbols like `µg/m³` that are device data, not language).

- **The interface is multi-language.** Every user-facing string goes through
  Home Assistant's translation system in `custom_components/addhon/translations/`
  (currently `en.json` and `it.json`), never hardcoded in the code:
  - **Entity names**: set `_attr_translation_key` (entities use
    `_attr_has_entity_name`) and add `entity.<platform>.<key>.name` to the
    translations. Do not set a hardcoded `name=` / `_attr_name`.
  - **Services**: keep the field schema/selectors in `services.yaml`; put the
    service and field `name`/`description` in the `services` block of the
    translations.
  - **User-facing errors**: raise
    `HomeAssistantError(translation_domain=DOMAIN, translation_key=..., translation_placeholders=...)`
    and add the message to the `exceptions` block. The `{placeholders}` in the
    message must match the keys passed in code.

`en.json` and `it.json` must keep an identical key structure (enforced by
`tests/test_translations.py` and `tests/test_entity_translation_keys.py`). Add a
key to both languages at once. Use plain text: no emoji, no long dashes.

> Sensor **state labels** (the textual values some sensors return, e.g. washer
> phases) are not yet localized; they are tracked as a follow-up (they need the
> `enum` device class plus `state` translations, which changes stored state
> values).

## Running the tests

```bash
python3 -B -m pytest tests/ -q
```

CI also runs `hassfest` and HACS validation. Keep the manifest `version` bumped
per change (major for breaking changes, e.g. entity friendly-name changes).
