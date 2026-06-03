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
        """Esegue il login ed estrae i dispositivi in modo sicuro da pyhOn."""
        try:
            if self._hon is None:
                _LOGGER.info("Inizializzazione della sessione pyhOn per %s...", self._username)
                self._hon = Hon(self._username, self._password)
                await self._hon.setup()

            appliances = []
            
            if not self._hon.appliances:
                _LOGGER.warning("Nessun dispositivo trovato sull'account hOn.")
                return appliances

            for appliance in self._hon.appliances:
                appliance_id = appliance.info.get("applianceId")
                if not appliance_id:
                    continue
                
                # Funzione di supporto interna per estrarre in sicurezza i valori da pyhOn v0.17.5
                def get_param_value(key, default=0):
                    try:
                        # In pyhOn si accede ai parametri tramite l'attributo .parameters
                        if key in appliance.parameters:
                            val = appliance.parameters[key].value
                            return val if val is not None else default
                        # Ripiego se la libreria espone la proprietà direttamente o tramite dizionario
                        val = appliance.get(key)
                        if hasattr(val, "value"):
                            return val.value
                        return val if val is not None else default
                    except Exception:
                        return default

                # Mappiamo i dati usando la funzione sicura che non va mai in crash
                appliance_data = {
                    "applianceId": appliance_id,
                    "shadow": {
                        "parameters": {
                            "onOffStatus": {"value": int(get_param_value("onOffStatus", 0))},
                            "machMode": {"value": int(get_param_value("machMode", 1))},
                            "tempSel": {"value": float(get_param_value("tempSel", 24))},
                            "compressorFrequency": {"value": float(get_param_value("compressorFrequency", 0))},
                            "tempIndoor": {"value": float(get_param_value("tempIndoor", 20))},
                            "tempOutdoor": {"value": float(get_param_value("tempOutdoor", 20))},
                        }
                    }
                }
                appliances.append(appliance_data)
                
            return appliances
        except Exception as err:
            _LOGGER.error("Errore critico durante il get_devices nel client API: %s", err)
            raise err

    async def set_device_status(self, appliance_id, parameters: dict):
        """Invia i comandi impostando i parametri direttamente sull'oggetto pyhOn."""
        try:
            if self._hon is None:
                return False
                
            for appliance in self._hon.appliances:
                if appliance.info.get("applianceId") == appliance_id:
                    for key, value in parameters.items():
                        # Usiamo l'approccio standard di pyhOn per inviare il comando
                        if key in appliance.parameters:
                            await appliance.parameters[key].set_value(value)
                        else:
                            await appliance.set_parameter(key, value)
                    return True
            return False
        except Exception as err:
            _LOGGER.error("Impossibile inviare il comando al dispositivo %s: %s", appliance_id, err)
            raise err