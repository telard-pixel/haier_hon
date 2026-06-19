"""Offline test del MQTT nativo (NativeMqttClient, Fase 3 piece 4b).

awscrt/awsiot sono stubati in sys.modules (il modulo li importa al top): così
testiamo a secco la logica NOSTRA — `stop()` (cancella+attende il watchdog, ferma
il client) e `_on_publish_received` (aggiorna parametri/connessione + notify, con i
rami difensivi) — senza rete né dipendenze native. Le parti che usano l'API awscrt
(`_start`/`_subscribe`) sono validate live.
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _mod(name: str) -> types.ModuleType:
    m = sys.modules.get(name)
    if m is None:
        m = types.ModuleType(name)
        sys.modules[name] = m
    return m


def _install_stubs() -> None:
    # homeassistant (lo importa custom_components/addhon/__init__.py)
    ce = _mod("homeassistant.config_entries")
    ce.ConfigEntry = getattr(ce, "ConfigEntry", type("ConfigEntry", (), {}))
    core = _mod("homeassistant.core")
    core.HomeAssistant = getattr(core, "HomeAssistant", type("HomeAssistant", (), {}))
    exc = _mod("homeassistant.exceptions")
    base = getattr(exc, "HomeAssistantError", type("HomeAssistantError", (Exception,), {}))
    exc.HomeAssistantError = base
    exc.ConfigEntryNotReady = getattr(exc, "ConfigEntryNotReady", type("ConfigEntryNotReady", (base,), {}))
    exc.ConfigEntryAuthFailed = getattr(exc, "ConfigEntryAuthFailed", type("ConfigEntryAuthFailed", (base,), {}))
    uc = _mod("homeassistant.helpers.update_coordinator")
    uc.DataUpdateCoordinator = getattr(uc, "DataUpdateCoordinator", type("DataUpdateCoordinator", (), {}))
    uc.UpdateFailed = getattr(uc, "UpdateFailed", type("UpdateFailed", (Exception,), {}))
    ha = _mod("homeassistant")
    ha.config_entries, ha.core, ha.exceptions = ce, core, exc
    ha.helpers = _mod("homeassistant.helpers")
    ha.helpers.update_coordinator = uc
    # awscrt.mqtt5 + awsiot.mqtt5_client_builder: bastano i nomi per l'import.
    awscrt = _mod("awscrt")
    awscrt.mqtt5 = _mod("awscrt.mqtt5")
    awsiot = _mod("awsiot")
    awsiot.mqtt5_client_builder = _mod("awsiot.mqtt5_client_builder")


_install_stubs()

from custom_components.addhon.client.transport.mqtt import NativeMqttClient  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class FakeParam:
    def __init__(self) -> None:
        self.updated = None

    def update(self, value) -> None:
        self.updated = value


class FakeAppliance:
    def __init__(self, topic: str) -> None:
        self.info = {"topics": {"subscribe": [topic]}}
        self.attributes = {"parameters": {"temp": FakeParam()}}
        self.nick_name = "Nick"
        self.connection = True
        self.synced = []

    def sync_params_to_command(self, name: str) -> None:
        self.synced.append(name)


class FakeHon:
    def __init__(self, appliances) -> None:
        self.api = object()
        self.appliances = appliances
        self.notified = 0

    def notify(self) -> None:
        self.notified += 1


def _packet(topic: str, payload: dict):
    return types.SimpleNamespace(
        publish_packet=types.SimpleNamespace(
            topic=topic, payload=json.dumps(payload).encode()
        )
    )


class StopTest(unittest.TestCase):
    def test_stop_cancels_watchdog_and_stops_client(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.stopped = False

            def stop(self) -> None:
                self.stopped = True

        async def body():
            m = NativeMqttClient(FakeHon([]), "MID")

            async def _forever():
                while True:
                    await asyncio.sleep(3600)

            m._watchdog_task = asyncio.ensure_future(_forever())
            await asyncio.sleep(0)  # lascia partire il watchdog
            client = FakeClient()
            m._client = client
            await m.stop()
            return m, client

        m, client = _run(body())
        self.assertTrue(client.stopped)
        self.assertIsNone(m._client)
        self.assertIsNone(m._watchdog_task)

    def test_stop_idempotent_no_client_no_task(self) -> None:
        m = NativeMqttClient(FakeHon([]), "MID")
        _run(m.stop())  # niente client/watchdog -> no-op, non solleva
        _run(m.stop())


class CreatePathTest(unittest.TestCase):
    """Drive il path REALE create()->_start->_subscribe->watchdog con stub awscrt
    più ricchi: cattura un errore di wiring (builder/subscribe) invisibile agli altri
    test (che mockano o saltano _start)."""

    def test_create_builds_client_and_subscribes(self) -> None:
        import awscrt
        import awsiot

        calls = {}

        class FakeSubResult:
            def result(self, timeout=None):
                return None

        class FakeClient:
            def __init__(self) -> None:
                self.started = False
                self.subscribed = []
                self.stopped = False

            def start(self) -> None:
                self.started = True

            def subscribe(self, packet) -> "FakeSubResult":
                self.subscribed.append(packet)
                return FakeSubResult()

            def stop(self) -> None:
                self.stopped = True

        fake_client = FakeClient()

        def fake_builder(**kwargs):
            calls["builder"] = kwargs
            return fake_client

        # stub runtime dell'API awscrt usata da _start/_subscribe
        awsiot.mqtt5_client_builder.websockets_with_custom_authorizer = fake_builder
        awscrt.mqtt5.SubscribePacket = lambda subs: ("pkt", subs)
        awscrt.mqtt5.Subscription = lambda topic: ("sub", topic)

        class FakeAuth:
            id_token = "IDT"

        class FakeApi:
            auth = FakeAuth()

            async def load_aws_token(self):
                return "SIGNED"

        app = FakeAppliance("haier/MAC/appliancestatus")
        hon = FakeHon([app])
        hon.api = FakeApi()

        async def body():
            # create + stop nello STESSO loop (il watchdog task è legato al loop)
            m = NativeMqttClient(hon, "MID")
            await m.create()
            had_watchdog = m._watchdog_task is not None
            await m.stop()
            return m, had_watchdog

        m, had_watchdog = _run(body())
        # builder chiamato con gli arg attesi
        b = calls["builder"]
        self.assertEqual(b["auth_authorizer_signature"], "SIGNED")
        self.assertEqual(b["auth_token_value"], "IDT")
        self.assertEqual(b["auth_token_key_name"], "token")
        self.assertTrue(b["client_id"].startswith("MID_"))
        # client avviato + subscribe per ogni topic + watchdog creato e poi fermato
        self.assertTrue(fake_client.started)
        self.assertEqual(len(fake_client.subscribed), 1)
        self.assertTrue(had_watchdog)
        self.assertTrue(fake_client.stopped)
        self.assertIsNone(m._watchdog_task)


class PublishReceivedTest(unittest.TestCase):
    def _client(self, appliance):
        hon = FakeHon([appliance])
        return NativeMqttClient(hon, "MID"), hon

    def test_appliancestatus_updates_params_and_notifies(self) -> None:
        topic = "haier/things/MAC/event/appliancestatus/update"
        app = FakeAppliance(topic)
        m, hon = self._client(app)
        m._on_publish_received(_packet(topic, {"parameters": [
            {"parName": "temp", "parValue": "5"},
            {"parName": "ignota", "parValue": "x"},  # non in parameters -> skip (difensivo)
        ]}))
        self.assertEqual(app.attributes["parameters"]["temp"].updated,
                         {"parName": "temp", "parValue": "5"})
        self.assertEqual(app.synced, ["settings"])
        self.assertEqual(hon.notified, 1)

    def test_disconnected_sets_connection_false(self) -> None:
        topic = "haier/things/MAC/event/disconnected"
        app = FakeAppliance(topic)
        m, hon = self._client(app)
        m._on_publish_received(_packet(topic, {"disconnectReason": "x"}))
        self.assertFalse(app.connection)
        self.assertEqual(hon.notified, 1)

    def test_connected_sets_connection_true(self) -> None:
        topic = "haier/things/MAC/event/connected"
        app = FakeAppliance(topic)
        app.connection = False
        m, hon = self._client(app)
        m._on_publish_received(_packet(topic, {}))
        self.assertTrue(app.connection)

    def test_unknown_topic_no_crash_no_notify(self) -> None:
        # topic che non corrisponde a nessun appliance -> esce senza crash (difensivo:
        # pyhOn faceva next(...) -> StopIteration).
        app = FakeAppliance("haier/known/appliancestatus")
        m, hon = self._client(app)
        m._on_publish_received(_packet("haier/UNKNOWN/topic", {"parameters": []}))
        self.assertEqual(hon.notified, 0)

    def test_empty_payload_ignored(self) -> None:
        app = FakeAppliance("t/appliancestatus")
        m, hon = self._client(app)
        m._on_publish_received(types.SimpleNamespace(publish_packet=None))
        self.assertEqual(hon.notified, 0)


if __name__ == "__main__":
    unittest.main()
