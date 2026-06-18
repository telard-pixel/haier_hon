"""pyhОn vendorizzato — SOLO il motore parser (commands/parameter/rules/appliance/
command_loader/attributes/diagnose).

Lo strato TRANSPORT di pyhОn (connection/auth/api/handler/device/mqtt + l'orchestratore
hon.Hon + la CLI __main__) è stato RIMOSSO: riscritto nativamente in
custom_components/addhon/client/ (vedi client/MIGRATION.md, Fase 3). Resta solo il
motore parser, bersaglio della Fase 4 (riscrittura finale = distacco totale).

Rigenerato da scripts/vendor_pyhon.py: non modificare a mano.
"""
