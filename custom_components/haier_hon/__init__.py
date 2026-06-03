import logging
from datetime import timedelta
import asyncio
import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["climate", "sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura l'integrazione Haier hOn partendo da un Config Entry."""
    # Supponiamo che tu stia usando una libreria client creata da Claude (es. HonApiClient)
    # Recuperiamo il client memorizzato (adatta se la classe ha un nome leggermente diverso)
     from .api import HonApiClient  # Modifica questo import se il file API ha un altro nome
    
    # Inizializziamo il client API (recuperando ipotetiche credenziali)
    # Se nel tuo vecchio __init__ avevi una logica di inizializzazione diversa, mantienila qui
    api_client = HonApiClient(entry.data.get("username"), entry.data.get("password"))

    # Creiamo il Coordinatore Centralizzato
    async def async_update_data():
        """Funzione interna che esegue l'unica chiamata di rete per tutti."""
        try:
            async with asyncio.timeout(10):
                devices = await api_client.get_devices()
                if not devices:
                    raise UpdateFailed("Nessun dispositivo restituito dall'API")
                
                # Mappiamo i dispositivi per applianceId per un accesso rapido
                return {device.get("applianceId"): device for device in devices if device.get("applianceId")}
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            raise UpdateFailed(f"Errore di comunicazione con l'API hOn: {err}") from err
        except Exception as ex:
            raise UpdateFailed(f"Errore imprevisto nel coordinatore Haier: {ex}") from ex

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Haier hOn data",
        update_method=async_update_data,
        update_interval=timedelta(seconds=30), # Una chiamata ogni 30 secondi per TUTTI
    )

    # Primo scaricamento dati all'avvio
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault("haier_hon", {})
    hass.data["haier_hon"][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Scarica l'config entry quando l'integrazione viene rimossa o disattivata."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data["haier_hon"].pop(entry.entry_id)
    return unload_ok