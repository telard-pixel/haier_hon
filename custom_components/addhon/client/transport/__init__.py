"""Transport nativo di addhОn (Fase 2 dello strangler).

Qui riscriviamo, pezzo per pezzo, lo strato auth/transport di pyhОn
(`_vendor/pyhon/connection/`) — quello FRAGILE, dove l'API Haier ci ha già rotto
(unified-api, token). Si costruisce bottom-up: prima i pezzi PURI (descrittore
device, parser di risposta), testati con differential test offline contro pyhОn;
poi HTTP/sessione e il flusso auth; infine il "flip" (pyhon_adapter.create_session
ritorna la sessione nativa invece del pyhon.Hon) e si cancella `_vendor`.

NB: codice RISCRITTO, non copiato. I valori-dato (es. versione app) rispecchiano
oggi pyhОn per non cambiare comportamento (verificato dai differential test); i
valori reali dell'app (vedi APK reverse) entreranno come passo deliberato e
validato a parte.
"""
