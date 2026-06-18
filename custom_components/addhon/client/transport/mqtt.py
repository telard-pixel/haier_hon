"""Client MQTT nativo addhОn (push realtime AWS IoT, Fase 3 piece 4b).

Riscrittura (non copia) di `_vendor/pyhon/connection/mqtt.MQTTClient` con awscrt
diretto: è l'ULTIMO pezzo di `_vendor/connection/` che ancora usavamo, quindi
riscriverlo qui sblocca la cancellazione di quella cartella.

Riceve la sessione (`NativeHon`) e ne legge `api` (token: `load_aws_token` +
`auth.id_token`), `appliances`, `notify` — tutto duck-typed: questo modulo resta
`_vendor`-free (gli `appliance` sono il motore parser pyhОn riusato, toccato solo
via la sua interfaccia pubblica).

Migliorie deliberate rispetto a pyhОn:
- un vero `stop()` (cancella+attende il watchdog PRIMA di fermare il client, così
  un `_start()` in volo non ricrea una connessione orfana) — pyhОn non lo aveva
  (leak di una connessione AWS IoT per reload);
- `_on_publish_received` difensivo: appliance non trovato per il topic / parametri
  mancanti -> skip invece del crash (pyhОn faceva `next(...)`/`payload["parameters"]`
  che sollevano). Identico a pyhОn quando ogni `parName` del messaggio è già presente
  in `attributes["parameters"]` (seminato dal poll HTTP `load_attributes`); un parName
  MQTT mai visto prima viene SALTATO (pyhОn crashava e non lo riteneva comunque; il
  successivo poll HTTP lo recupera). Quando il motore sarà nostro (Fase 4) potremo
  crearne la voce al volo senza dipendere da `_vendor`.

awscrt/awsiot sono importati al top (come pyhОn): il modulo NON è importabile a
secco; chi lo usa (`NativeHon`) lo importa lazy. Il rumore INFO del lifecycle è
governato da `logging_utils` su questo logger.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
from typing import Any

from awscrt import mqtt5
from awsiot import mqtt5_client_builder  # type: ignore[import-untyped]

from .device import MOBILE_ID

_LOGGER = logging.getLogger(__name__)

# Endpoint/authorizer AWS IoT del cloud hОn (da pyhОn const.py).
AWS_ENDPOINT = "a30f6tqw0oh1x0-ats.iot.eu-west-1.amazonaws.com"
AWS_AUTHORIZER = "candy-iot-authorizer"

_WATCHDOG_INTERVAL = 5  # secondi
_SUBSCRIBE_TIMEOUT = 10  # secondi


class NativeMqttClient:
    """Push realtime via AWS IoT MQTT5 sopra la sessione nativa."""

    def __init__(self, hon: Any, mobile_id: str) -> None:
        self._hon = hon
        self._mobile_id = mobile_id or MOBILE_ID
        self._api = hon.api
        self._appliances = hon.appliances
        self._client: mqtt5.Client | None = None
        self._connection = False
        self._watchdog_task: asyncio.Task[None] | None = None

    @property
    def client(self) -> mqtt5.Client:
        if self._client is None:
            raise AttributeError("client MQTT non avviato")
        return self._client

    async def create(self) -> "NativeMqttClient":
        await self._start()
        self._subscribe_appliances()
        await self._start_watchdog()
        return self

    async def stop(self) -> None:
        """Ferma watchdog (cancella+attende) e poi il client awscrt. Idempotente."""
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            except Exception as err:  # pragma: no cover - difensivo
                _LOGGER.debug("addhОn: attesa cancel watchdog MQTT fallita: %s", err)
            self._watchdog_task = None
        if self._client is not None:
            try:
                self._client.stop()
            except Exception as err:  # pragma: no cover - difensivo
                _LOGGER.debug("addhОn: stop client MQTT fallito: %s", err)
            self._client = None

    # ── lifecycle callbacks ───────────────────────────────────────────────────
    def _on_lifecycle_stopped(self, data: "mqtt5.LifecycleStoppedData") -> None:
        _LOGGER.info("Lifecycle Stopped: %s", data)

    def _on_lifecycle_connection_success(
        self, data: "mqtt5.LifecycleConnectSuccessData"
    ) -> None:
        self._connection = True
        _LOGGER.info("Lifecycle Connection Success: %s", data)

    def _on_lifecycle_attempting_connect(
        self, data: "mqtt5.LifecycleAttemptingConnectData"
    ) -> None:
        _LOGGER.info("Lifecycle Attempting Connect: %s", data)

    def _on_lifecycle_connection_failure(
        self, data: "mqtt5.LifecycleConnectFailureData"
    ) -> None:
        self._connection = False
        _LOGGER.info("Lifecycle Connection Failure: %s", data)

    def _on_lifecycle_disconnection(
        self, data: "mqtt5.LifecycleDisconnectData"
    ) -> None:
        self._connection = False
        _LOGGER.info("Lifecycle Disconnection: %s", data)

    def _on_publish_received(self, data: "mqtt5.PublishReceivedData") -> None:
        if not (data and data.publish_packet and data.publish_packet.payload):
            return
        payload = json.loads(data.publish_packet.payload.decode())
        topic = data.publish_packet.topic
        # Difensivo (pyhОn faceva next(...) -> StopIteration): appliance non trovato -> esci.
        appliance = next(
            (
                a
                for a in self._appliances
                if topic in a.info.get("topics", {}).get("subscribe", [])
            ),
            None,
        )
        if appliance is None:
            _LOGGER.debug("MQTT: topic senza appliance corrispondente: %s", topic)
            return
        if topic and "appliancestatus" in topic:
            params = appliance.attributes.get("parameters", {})
            for parameter in payload.get("parameters", []):
                name = parameter.get("parName")
                # Solo parametri già noti (seminati da load_attributes). Un parName
                # nuovo si recupera al prossimo poll HTTP; crearlo qui legherebbe
                # questo modulo a _vendor (HonAttribute) -> rimandato a Fase 4.
                if name in params:
                    params[name].update(parameter)
            appliance.sync_params_to_command("settings")
        elif topic and "disconnected" in topic:
            _LOGGER.info(
                "Disconnected %s: %s",
                appliance.nick_name,
                payload.get("disconnectReason"),
            )
            appliance.connection = False
        elif topic and "connected" in topic:
            appliance.connection = True
            _LOGGER.info("Connected %s", appliance.nick_name)
        elif topic and "discovery" in topic:
            _LOGGER.info("Discovered %s", appliance.nick_name)
        self._hon.notify()
        _LOGGER.info("%s - %s", topic, payload)

    # ── connessione / subscribe / watchdog ────────────────────────────────────
    async def _start(self) -> None:
        self._client = mqtt5_client_builder.websockets_with_custom_authorizer(
            endpoint=AWS_ENDPOINT,
            auth_authorizer_name=AWS_AUTHORIZER,
            auth_authorizer_signature=await self._api.load_aws_token(),
            auth_token_key_name="token",
            auth_token_value=self._api.auth.id_token,
            client_id=f"{self._mobile_id}_{secrets.token_hex(8)}",
            on_lifecycle_stopped=self._on_lifecycle_stopped,
            on_lifecycle_connection_success=self._on_lifecycle_connection_success,
            on_lifecycle_attempting_connect=self._on_lifecycle_attempting_connect,
            on_lifecycle_connection_failure=self._on_lifecycle_connection_failure,
            on_lifecycle_disconnection=self._on_lifecycle_disconnection,
            on_publish_received=self._on_publish_received,
        )
        self.client.start()

    def _subscribe_appliances(self) -> None:
        for appliance in self._appliances:
            self._subscribe(appliance)

    def _subscribe(self, appliance: Any) -> None:
        for topic in appliance.info.get("topics", {}).get("subscribe", []):
            self.client.subscribe(
                mqtt5.SubscribePacket([mqtt5.Subscription(topic)])
            ).result(_SUBSCRIBE_TIMEOUT)
            _LOGGER.info("Subscribed to topic %s", topic)

    async def _start_watchdog(self) -> None:
        if not self._watchdog_task or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self._watchdog())

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(_WATCHDOG_INTERVAL)
            if not self._connection:
                _LOGGER.info("Restart mqtt connection")
                await self._start()
                self._subscribe_appliances()
