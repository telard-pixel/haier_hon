# Architettura del client hОn nativo di addhОn

L'integrazione NON dipende da pyhОn: tutto il client (auth/transport, motore
comandi/parametri/rules, appliance) è codice NOSTRO in `client/`. La libreria pyhОn,
un tempo vendorizzata in `../_vendor/pyhon/`, è stata sostituita interamente e
cancellata (migrazione strangler completa, vedi "Storia").

## Strati

- `interfaces.py` — i Protocol che definiscono la superficie del client da cui dipende
  l'integrazione (duck-typed). Contratto stretto e verificabile, senza dipendenze.
- `pyhon_adapter.py` — factory: `create_session()` -> `session.NativeHon`,
  `create_appliance()` -> `engine.appliance.HonAppliance`. Disaccoppia `hon_client.py`
  dai dettagli del client.
- `session.py` (`NativeHon`) — orchestrazione: login + load_appliances, costruzione
  appliance, MQTT. Context manager async; soddisfa `interfaces.HonSession`.
- `transport/` — auth/HTTP/MQTT nativi (Salesforce OAuth, `HonConnection`, `HonApi`,
  `NativeMqttClient` su awscrt). Rimpiazza l'ex `_vendor/pyhon/connection/`.
- `engine/` — motore parser nativo: `parameter/` (range/enum/fixed/program),
  `attributes.py`, `commands.py`, `command_loader.py`, `rules.py`, `appliances/`
  (layer per-tipo + registry statico), `appliance.py` (ROOT).
- Sopra al client sta la mappatura dichiarativa dell'integrazione (`const.py`,
  `sensor.py`, `binary_sensor.py`, `number.py`, ...): indipendente dagli interni del client.

## Principi (mantenuti dalla migrazione)

- Codice NOSTRO, non copia: più moderno, validato sui dump reali (`apk/dump/`) e
  sull'app decompilata (`apk/analysis/`).
- Fedeltà byte-a-byte SOLO dove i valori vanno al cloud e non sono validabili offline
  (richieste HTTP, payload comando). Altrove, dove pyhОn aveva un bug e sappiamo fare
  meglio (validato live/app), **divergiamo e documentiamo**: es. fix BABYCARE nell'enum,
  condizioni-extra delle rules, `$installationType`, connettività da `lastConnEvent`,
  timestamp comando.
- I test ex-differential (oracolo pyhОn) sono diventati golden (`tests/golden/*.json` +
  `tests/_golden.py`): l'output nativo, provato == pyhОn, è congelato come regressione
  (rigenera con `GEN_GOLDEN=1`).

## Regole di confine

1. `interfaces.py` è SENZA dipendenze (solo `typing`).
2. Il corpo dell'integrazione dipende dai Protocol di `interfaces.py`, non dagli oggetti
   concreti del client.
3. Nessun file importa più `_vendor` (cancellato); guardia in
   `tests/test_session_adapter.py` (zero import `_vendor` + dir assente).

## Provenienza della mappatura

- `dump-validated` — confermato da un dump reale (frigo REF HDPW5620CNPK, AC live).
- `app-mapping` — dalla mappatura decompilata (`apk/analysis/`, ampia, non sempre live).

## Storia (strangler, completa)

Migrazione un pezzo alla volta, **per fragilità non per facilità**: prima il transport
(fragile: unified-api/token), poi il motore comandi/parametri (stabile), infine la
cancellazione di `_vendor/`. Dettaglio fase-per-fase, decisioni e reverse-engineering in
`diagnostics/FASE4-engine-plan.md`, `apk/analysis/` e nei messaggi di commit. Esito:
distacco TOTALE da pyhОn, validato live sui device reali (AC/REF/TD/WM).
