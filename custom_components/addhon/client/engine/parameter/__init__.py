"""Native parameter classes (range/enum/fixed) + base.

Rewrite of pyhOn's `parameter/`. Behavior anchored to pyhOn by the
differential test (tests/test_engine_parameters.py) against the real fridge parameters
(apk/dump/ref_10136/commands.json), with ONE intentional divergence: the fix for the
BABYCARE bug in HonParameterEnum's setter (comparison on the normalized value).
"""
