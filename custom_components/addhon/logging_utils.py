"""Controllo dei livelli di log diagnostici per l'integrazione.

Il client MQTT (ora il NOSTRO ``client.transport.mqtt``; prima pyhОn) emette a
livello INFO un messaggio per ogni tentativo di (ri)connessione realtime
("Lifecycle Attempting Connect / Connection Failure / Disconnection / Connection
Success").
Quando lo slot di push è conteso (es. l'elettrodomestico è condiviso e il
proprietario tiene il canale), questi tentativi falliscono in un ciclo continuo
e riempiono il log senza che ci sia nulla da fare lato integrazione: i dati
restano comunque aggiornati via polling.

Di default abbassiamo quel logger a WARNING (i tentativi spariscono, eventuali
warning/errori reali restano). Il service ``addhon.set_mqtt_log_level``
rialza il livello al volo (es. ``debug``) per diagnosticare i problemi di
realtime, e lo riabbassa a ``warning`` per risilenziare.

Nessun import intra-package o da homeassistant: il modulo è caricabile in
isolamento (via importlib) e quindi testabile senza stub di Home Assistant.
"""
from __future__ import annotations

import logging

# Namespace del pyhОn vendorizzato: i suoi moduli loggano sotto questo prefisso
# (il nome del logger == __name__ del modulo). NON è coupling da rimuovere: sono
# i nomi REALI dei logger di cui regoliamo il livello. Tenuto come UNICA costante
# così, quando il transport nativo sostituirà pyhОn (vedi client/MIGRATION.md),
# c'è un solo punto da aggiornare.
_VENDOR_NS = "custom_components.addhon._vendor.pyhon"

# Logger da alzare/abbassare quando serve diagnosticare discovery, setup,
# reauth e polling. Il logger MQTT resta controllato separatamente sotto
# MQTT_NOISE_LOGGERS, così il debug discovery non riaccende il rumore realtime.
INTEGRATION_DEBUG_LOGGERS: tuple[str, ...] = (
    "custom_components.addhon",
    _VENDOR_NS,
    "pyhon",
)

# Logger responsabili del rumore MQTT realtime. Dopo il transport nativo il client
# MQTT è il NOSTRO (`client.transport.mqtt`); teniamo anche i nomi pyhОn finché il
# vendor non sparisce, così il controllo del livello copre vecchio e nuovo.
MQTT_NOISE_LOGGERS: tuple[str, ...] = (
    "custom_components.addhon.client.transport.mqtt",
    f"{_VENDOR_NS}.connection.mqtt",
    "pyhon.connection.mqtt",
)

# Livello applicato di default: nasconde i tentativi INFO/DEBUG, lascia passare
# warning ed errori reali.
DEFAULT_MQTT_LOG_LEVEL = logging.WARNING

# Nomi di livello accettati dal service, mappati sui valori del modulo logging.
MQTT_LOG_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def apply_mqtt_log_level(level: int) -> None:
    """Imposta ``level`` su tutti i logger MQTT rumorosi di pyhOn."""
    for name in MQTT_NOISE_LOGGERS:
        logging.getLogger(name).setLevel(level)


def apply_integration_log_level(level: int) -> None:
    """Imposta ``level`` sui logger utili a debug setup/discovery/polling."""
    for name in INTEGRATION_DEBUG_LOGGERS:
        logging.getLogger(name).setLevel(level)


def silence_mqtt_noise() -> None:
    """Applica il livello di default: silenzia i tentativi di riconnessione."""
    apply_mqtt_log_level(DEFAULT_MQTT_LOG_LEVEL)
