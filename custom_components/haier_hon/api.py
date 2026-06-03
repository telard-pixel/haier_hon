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
        """Esegue il login (se necessario) e mappa i dispositivi reali di pyhOn."""
        try:
            if self._hon is None:
                _LOGGER.info("Inizializzazione della sessione pyhOn per %s...", self._username)
                # Inizializza la libreria pyhOn ed effettua il login ai server Haier
                self._hon = Hon(self._username, self._password)
                await self._hon.setup()

            appliances = []
            
            # Nella v0.17.5, self._hon.appliances contiene la lista degli oggetti reali
            for appliance in self._hon.appliances:
                appliance_id = appliance.info.get("applianceId")
                if not appliance_id:
                    continue
                    
                # Mappiamo i dati estraendoli direttamente dall'oggetto pyhOn
                appliance_data = {
                    "applianceId": appliance_id,
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
            _LOGGER.error("Errore critico nel recupero dei dispositivi hOn: %s", err)
            raise err

    async def set_device_status(self, appliance_id, parameters: dict):
        """Invia i comandi impostando i parametri direttamente sull'oggetto pyhOn."""
        try:
            if self._hon is None:
                return False
                
            for appliance in self._hon.appliances:
                if appliance.info.get("applianceId") == appliance_id:
                    # pyhOn gestisce l'invio aggiornando i singoli parametri dell'oggetto
                    for key, value in parameters.items():
                        await appliance.set_parameter(key, value)
                    return True
            return False
        except Exception as err:
            _LOGGER.error("Impossibile inviare il comando al dispositivo %s: %s", appliance_id, err)
            raise err