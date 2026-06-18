"""Motore parser nativo di addhОn (Fase 4 dello strangler).

Riscrive — pezzo per pezzo, bottom-up — il "motore" di pyhОn (commands/parameter/
rules/command_loader/appliance), l'ultimo strato ancora vendorizzato in
`_vendor/pyhon/`. Obiettivo: distacco TOTALE da pyhОn con codice NOSTRO, più
moderno e validato sui dump reali + sull'app decompilata (vedi client/MIGRATION.md
e diagnostics/FASE4-engine-plan.md).

Metodo: ogni pezzo è riscritto (non copiato), differential-testato contro pyhОn
(oracolo = i dump reali in `apk/dump/`), e il flip dei chiamanti avviene quando il
cluster coeso (commands↔parameter↔rules) è pronto — perché `rules.py` di pyhОn usa
`isinstance` contro le SUE classi parametro, quindi i parametri non si possono
flippare da soli senza rompere le rules. Slice 1 = parametri (qui), validati in
isolamento; il flip in produzione arriva col cluster.
"""
