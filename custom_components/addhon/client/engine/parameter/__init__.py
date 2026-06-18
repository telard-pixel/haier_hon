"""Classi parametro native (range/enum/fixed) + base.

Riscrittura di `_vendor/pyhon/parameter/`. Comportamento ancorato a pyhОn dal
differential test (tests/test_engine_parameters.py) sui parametri reali del frigo
(apk/dump/ref_10136/commands.json), con UNA divergenza voluta: il fix del bug
BABYCARE nel setter di HonParameterEnum (confronto su valore normalizzato).
"""
