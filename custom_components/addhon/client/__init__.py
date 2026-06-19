"""Native hOn client of addhOn.

The whole client (auth/transport, command/parameter/rules engine, appliance) is OUR
code: the pyhOn library (once vendored in `../_vendor/pyhon/`) has been entirely
replaced and deleted.

Boundary rule: the body of the integration does not depend on the concrete client
objects but on the Protocols in `interfaces.py`. The factory in `pyhon_adapter.py`
builds the native session and appliance.

Migration history (strangler pattern, now complete) in MIGRATION.md.
"""
