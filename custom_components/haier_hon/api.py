import logging
import asyncio
from pyhon import Hon

_LOGGER = logging.getLogger(__name__)

class HonApiClient:
    """Client per comunicare con l'API Cloud hOn di Haier tramite pyhOn."""

    def __init__(self, username, password):
        self._username = username
        self._password = password
        self._hon = None

async def get_devices(self):
        """Esegue il login (se necessario) e recupera tutti i dispositivi."""
        try:
            if self._hon is None:
                # Inizializza la libreria pyhOn ed effettua il login ai server Haier
                self._hon = await Hon(self._username, self._password)
                await self._hon.setup()

            appliances = []
            for appliance in self._hon.appliances:
                # Costruiamo la struttura dati che si aspettano climate.py e sensor.py
                appliance_data = {
                    "applianceId": appliance.info.get("applianceId"),
                    "shadow": {
                        "parameters": {
                            "onOffStatus": {"value": int(appliance.get("onOffStatus", 0))},
                            "machMode": {"value": int(appliance.get("machMode", 1))},
                            "tempSel": {"value": float(appliance.get("tempSel", 24))},
                            "compressorFrequency": {"value": float(appliance.get("compressorFrequency", 0))},
                            "tempIndoor": {"value": float(appliance.get("tempIndoor", 20))},
                            "tempOutdoor": {"value": float(appliance.get("tempOutdoor", 20))},
                        }
                    }
                }
                appliances.append(appliance_data)
                
            return appliances
        except Exception as err:
            _LOGGER.error("Errore nel recupero dei dispositivi hOn reali: %s", err)
            raise err