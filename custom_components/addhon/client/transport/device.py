"""Descrittore del device client per il transport addhOn.

Riscrittura nativa di `_vendor/pyhon/connection/device.HonDevice`: il "chi sono"
(app version, OS, modello, mobileId) inviato al cloud hOn in ogni richiesta.

I valori sotto rispecchiano OGGI quelli di pyhOn, così il payload è identico e
il differential test (tests/test_transport_device.py) lo verifica contro la
classe pyhOn reale. Quando avremo il flusso/identità reali dell'app (vedi APK
reverse: appVersion 2.x, deviceModel "BVL", osVersion 34, mobileId vero) qui
andranno quei valori, come passo separato e validato.
"""
from __future__ import annotations

from dataclasses import dataclass

# Identità client (valori-dato che oggi rispecchiano pyhOn; punto unico da
# aggiornare per impersonare l'app reale).
APP_VERSION = "2.6.5"
OS_VERSION = 999
OS = "android"
DEVICE_MODEL = "pyhOn"
MOBILE_ID = "pyhOn"


@dataclass(frozen=True)
class HonDevice:
    """Descrittore immutabile del client. `mobile_id` vuoto ricade sul default."""

    mobile_id: str = MOBILE_ID

    def __post_init__(self) -> None:
        if not self.mobile_id:
            object.__setattr__(self, "mobile_id", MOBILE_ID)

    def payload(self, mobile: bool = False) -> dict[str, str | int]:
        """Il dizionario identità inviato al cloud.

        Con `mobile=True` la chiave `os` diventa `mobileOs` (come fa l'app per le
        chiamate "mobile"); è la stessa trasformazione di pyhOn.
        """
        data: dict[str, str | int] = {
            "appVersion": APP_VERSION,
            "mobileId": self.mobile_id,
            "os": OS,
            "osVersion": OS_VERSION,
            "deviceModel": DEVICE_MODEL,
        }
        if mobile:
            data["mobileOs"] = data.pop("os")
        return data
