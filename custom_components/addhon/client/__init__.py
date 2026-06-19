"""Client hOn nativo di addhOn.

Tutto il client (auth/transport, motore comandi/parametri/rules, appliance) è codice
NOSTRO: la libreria pyhOn (un tempo vendorizzata in `../_vendor/pyhon/`) è stata
sostituita interamente e cancellata.

Regola di confine: il corpo dell'integrazione non dipende dagli oggetti concreti del
client ma dai Protocol in `interfaces.py`. La factory in `pyhon_adapter.py` costruisce
sessione e appliance native.

Storia della migrazione (strangler pattern, ora completa) in MIGRATION.md.
"""
