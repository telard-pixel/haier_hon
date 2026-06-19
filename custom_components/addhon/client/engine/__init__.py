"""Motore parser nativo di addhOn (comandi/parametri/rules/program/appliance).

Codice NOSTRO che ha sostituito il "motore" un tempo vendorizzato di pyhOn
(commands/parameter/rules/command_loader/appliance), più moderno e validato sui dump
reali + sull'app decompilata (vedi client/MIGRATION.md, diagnostics/FASE4-engine-plan.md
e apk/analysis/). pyhOn è stato cancellato.

Vincolo di design: `rules.py` usa `isinstance` contro le classi parametro; per questo
parametri, comandi, rules, program e layer per-tipo sono un cluster coeso che vive e si
evolve insieme. Comportamento ancorato ai dump reali dai golden test (tests/golden/).
"""
