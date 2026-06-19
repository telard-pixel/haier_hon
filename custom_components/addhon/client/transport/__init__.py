"""Native addhOn transport (auth/HTTP/MQTT).

Auth/transport layer written from scratch, which replaced the former
`_vendor/pyhon/connection/` (the FRAGILE one, where the Haier API had already broken
us: unified-api, tokens). Pure pieces (device descriptor, response parser), then
HTTP/session and the auth flow (Salesforce OAuth), then the MQTT client (awscrt).

NB: REWRITTEN code, not copied. The data values (e.g. app version) are the
historical ones for behavior compatibility; the real values from the APK reverse enter
as a deliberate, separately validated step.
"""
