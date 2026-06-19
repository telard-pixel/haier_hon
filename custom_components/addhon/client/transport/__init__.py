"""Transport nativo di addhOn (auth/HTTP/MQTT).

Strato auth/transport scritto da zero, che ha rimpiazzato l'ex
`_vendor/pyhon/connection/` (quello FRAGILE, dove l'API Haier ci aveva già rotto:
unified-api, token). Pezzi puri (descrittore device, parser di risposta), poi
HTTP/sessione e il flusso auth (Salesforce OAuth), poi il client MQTT (awscrt).

NB: codice RISCRITTO, non copiato. I valori-dato (es. versione app) sono quelli
storici per compatibilità di comportamento; i valori reali dall'APK reverse entrano
come passo deliberato e validato a parte.
"""
