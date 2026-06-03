import logging
import asyncio
from pyhon import Hon

_LOGGER = logging.getLogger(__name__)

class HonApiClient:
    """Client ufficiale per comunicare con l'API Cloud hOn di Haier tramite pyhOn v0.17.5."""

    def __init__(self, username, password):
        self._username = username
        self._password = password
        self._hon = None

    async def get_devices(self):
        """Effettua il login definitivo passando le chiavi nominali corrette alla libreria."""
        try:
            if self._hon is None:
                _LOGGER.info("Inizializzazione sessione hOn per l'utente: %s", self._username)
                
                # PATCH IN TEMPO REALE PER L'ASCIUGATRICE (Bug BABYCARE di pyhOn)
                from pyhon.parameter.enum import HonParameterEnum
                original_value_setter = HonParameterEnum.value.fset

                def patched_value_setter(instance, value):
                    try:
                        original_value_setter(instance, value)
                    except ValueError as value_err:
                        if str(value) in str(instance._values) or value == str(instance._values)[1:-1].replace("'", ""):
                            _LOGGER.debug("Patch ENUM applicata con successo per il valore: %s", value)
                            instance._value = value
                        else:
                            raise value_err

                HonParameterEnum.value = property(HonParameterEnum.value.fget, patched_value_setter, HonParameterEnum.value.fdel)

                # CHIAMATA CORRETTA PER v0.17.5: Usiamo le chiavi esplicite email= e password=
                hon_instance = Hon(email=self._username, password=self._password)

                # Avviamo il contesto persistente manualmente
                if hasattr(hon_instance, "__aenter__"):
                    await hon_instance.__aenter__()
                
                # Eseguiamo il setup dei dispositivi scaricando i dati dal cloud
                _LOGGER.info("Esecuzione del setup dei dispositivi...")
                await hon_instance.setup()
                
                self._hon = hon_instance
                _LOGGER.info("Connessione ai server Cloud Haier hOn stabilita con successo.")

            appliances = []
            
            # Recuperiamo l'elenco dei dispositivi dall'istanza persistente
            appliances_list = getattr(self._hon, "appliances", None)
            if not appliances_list:
                _LOGGER.warning("Nessun dispositivo associato all'account hOn specificato.")
                return appliances

            for appliance in appliances_list:
                appliance_id = appliance.info.get("applianceId") or getattr(appliance, "id", None)
                if not appliance_id:
                    continue

                # Estrazione dello stato dei sensori dal dizionario nativo .data
                device_raw_data = getattr(appliance, "data", {})

                # Struttura dati shadow coerente per il coordinatore di Home Assistant
                appliance_data = {
                    "applianceId": str(appliance_id),
                    "shadow": {
                        "parameters": {
                            "onOffStatus": {"value": int(device_raw_data.get("onOffStatus", 0))},
                            "machMode": {"value": int(device_raw_data.get("machMode", 1))},
                            "tempSel": {"value": float(device_raw_data.get("tempSel", 24.0))},
                            "compressorFrequency": {"value": float(device_raw_data.get("compressorFrequency", 0.0))},
                            "tempIndoor": {"value": float(device_raw_data.get("tempIndoor", 20.0))},
                            "tempOutdoor": {"value": float(device_raw_data.get("tempOutdoor", 20.0))},
                        }
                    }
                }
                appliances.append(appliance_data)
                
            return appliances

        except Exception as err:
            _LOGGER.error("Errore critico definitivo di comunicazione con pyhOn: %s", err, exc_info=True)
            self._hon = None
            raise err

    async def set_device_status(self, appliance_id, parameters: dict):
        """Invia i comandi di controllo modificando le impostazioni dell'appliance sul cloud."""
        try:
            if self._hon is None:
                _LOGGER.error("Impossibile inviare comandi: la sessione hOn non è inizializzata o è scaduta.")
                return False
                
            for appliance in self._hon.appliances:
                current_id = appliance.info.get("applianceId") or getattr(appliance, "id", None)
                if str(current_id) == str(appliance_id):
                    for key, value in parameters.items():
                        if hasattr(appliance, "set_parameter"):
                            await appliance.set_parameter(key, value)
                        elif hasattr(appliance, "parameters") and key in appliance.parameters:
                            await appliance.parameters[key].set_value(value)
                    return True
            return False
        except Exception as err:
            _LOGGER.error("Impossibile inviare il comando al dispositivo %s: %s", appliance_id, err, exc_info=True)
            raise err