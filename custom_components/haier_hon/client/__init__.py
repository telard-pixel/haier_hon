"""Client hОn nativo di addhОn — sostituto progressivo del pyhОn vendorizzato.

Questa cartella è il "nuovo" codice: ci migriamo dentro un pezzo alla volta,
mentre `../_vendor/pyhon/` (il fork vendorizzato, rigenerato da
scripts/vendor_pyhon.py, NON modificabile a mano) si svuota progressivamente
fino a sparire.

Regola di confine: il codice in `client/` NON importa mai da `_vendor.pyhon`
direttamente, tranne l'unico adattatore-ponte previsto durante la transizione.
Tutto il resto dell'integrazione deve dipendere dai Protocol in `interfaces.py`,
non dagli oggetti concreti di pyhОn.

Vedi MIGRATION.md per il piano a fasi (strangler pattern, transport per primo).
"""
