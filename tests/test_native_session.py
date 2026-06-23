"""Offline test of the native `Hon` orchestration (NativeHon, Phase 3 piece 3).

Verifies the setup SEQUENCE faithful to pyhOn `Hon.setup` (load_appliances ->
per appliance load_commands/attributes/statistics -> MQTT last), zone handling,
the empty-mac skip, per-appliance error tolerance, MQTT gating, close, and
conformance to the `HonSession` Protocol.

The pyhOn engine (HonAppliance) and MQTT are mocked via the `factory`
factories (the only bridge to `_vendor`): no `_vendor` import, no network, no
awscrt. aiohttp/yarl/homeassistant are stubbed.
"""
from __future__ import annotations

import asyncio
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
    yarl = _mod("yarl")
    if not hasattr(yarl, "URL"):
        yarl.URL = type("URL", (), {"__init__": lambda self, s, encoded=False: None})
    aio = _mod("aiohttp")
    aio.ClientSession = getattr(aio, "ClientSession", type("ClientSession", (), {}))
    aio.ClientResponse = getattr(aio, "ClientResponse", type("ClientResponse", (), {}))
    aio.ContentTypeError = getattr(aio, "ContentTypeError", type("ContentTypeError", (Exception,), {}))


_install_stubs()

from custom_components.addhon.client import factory  # noqa: E402
from custom_components.addhon.client import session as session_mod  # noqa: E402
from custom_components.addhon.client.session import NativeHon  # noqa: E402
from custom_components.addhon.client.interfaces import HonSession  # noqa: E402
from custom_components.addhon.client.transport.auth import NativeAuthError  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class FakeAppliance:
    def __init__(self, api, data, zone, events, fail=False) -> None:
        self._api = api
        self._data = data
        self.zone = zone
        self.events = events
        self.fail = fail
        self.mac_address = data.get("macAddress", "")
        self.appliance_type = data.get("applianceTypeName", "?")

    async def load_commands(self) -> None:
        self.events.append(f"cmd:{self.mac_address}:{self.zone}")
        if self.fail:
            raise KeyError("boom")

    async def load_attributes(self) -> None:
        self.events.append(f"attr:{self.mac_address}:{self.zone}")

    async def load_statistics(self) -> None:
        self.events.append(f"stat:{self.mac_address}:{self.zone}")


class FakeApi:
    def __init__(self, appliances, events) -> None:
        self._appliances = appliances
        self.events = events
        self.closed = False

    async def load_appliances(self):
        self.events.append("load_appliances")
        return [dict(a) for a in self._appliances]

    async def close(self):
        self.closed = True


class FakeMqtt:
    def __init__(self, harness) -> None:
        self._harness = harness
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True
        self._harness.stop_calls.append(self)


class _Harness:
    """Patches create_appliance (factory) + NativeHon._make_mqtt + HonConnection/HonApi."""

    def __init__(self, test, appliances, fail_macs=()):
        self.test = test
        self.events: list = []
        self.appliances_data = appliances
        self.fail_macs = set(fail_macs)
        self.api = FakeApi(appliances, self.events)
        self.mqtt_calls: list = []
        self.stop_calls: list = []
        self.mqtt_instance = None

    def install(self):
        h = self  # harness (avoids collision with self=NativeHon in the patched methods)
        t = self.test
        events = self.events

        def fake_create_appliance(api, data, zone=0):
            return FakeAppliance(api, data, zone, events, fail=data.get("macAddress") in h.fail_macs)

        async def fake_make_mqtt(hon):  # hon = NativeHon instance (bound method)
            events.append("mqtt")
            m = FakeMqtt(h)
            h.mqtt_calls.append((hon, hon._mobile_id))
            h.mqtt_instance = m
            return m

        t._patch(factory, "create_appliance", fake_create_appliance)
        t._patch(NativeHon, "_make_mqtt", fake_make_mqtt)


class NativeSessionSetupTest(unittest.TestCase):
    def _patch(self, obj, name, value):
        real = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(lambda: setattr(obj, name, real))

    def _nh_with_api(self, harness, **kw):
        nh = NativeHon("u@x", "p", **kw)
        nh._api = harness.api  # bypass connection creation, test setup()
        return nh

    def test_setup_loads_each_appliance_then_mqtt_last(self) -> None:
        data = [
            {"macAddress": "A", "applianceTypeName": "REF"},
            {"macAddress": "B", "applianceTypeName": "WM"},
        ]
        h = _Harness(self, data)
        h.install()
        nh = self._nh_with_api(h)
        _run(nh.setup())
        # 2 appliances built + loaded, mqtt LAST
        self.assertEqual([a.mac_address for a in nh.appliances], ["A", "B"])
        self.assertEqual(h.events[0], "load_appliances")
        self.assertEqual(h.events[-1], "mqtt")
        # for each appliance: cmd -> attr -> stat, and all BEFORE mqtt
        self.assertEqual(
            h.events,
            ["load_appliances",
             "cmd:A:0", "attr:A:0", "stat:A:0",
             "cmd:B:0", "attr:B:0", "stat:B:0",
             "mqtt"],
        )

    def test_zone_appliance_split(self) -> None:
        data = [{"macAddress": "Z", "applianceTypeName": "AC", "zone": "2"}]
        h = _Harness(self, data)
        h.install()
        nh = self._nh_with_api(h)
        _run(nh.setup())
        # zones=2 -> zone1, zone2, then base(zone0) = 3 appliances (like pyhOn)
        self.assertEqual([a.zone for a in nh.appliances], [1, 2, 0])

    def test_zero_appliances_still_creates_mqtt(self) -> None:
        # 0 appliances: load_appliances (=1 authenticated POST that populates the tokens)
        # still happens, then MQTT still starts -> auth ready even without appliances.
        h = _Harness(self, [])
        h.install()
        nh = self._nh_with_api(h)
        _run(nh.setup())
        self.assertEqual(nh.appliances, [])
        self.assertEqual(h.events, ["load_appliances", "mqtt"])
        self.assertEqual(len(h.mqtt_calls), 1)

    def test_mqtt_created_once_across_two_setups(self) -> None:
        # the `not self._mqtt_client` gate prevents a second MQTT creation.
        data = [{"macAddress": "A", "applianceTypeName": "REF"}]
        h = _Harness(self, data)
        h.install()
        nh = self._nh_with_api(h)
        _run(nh.setup())
        _run(nh.setup())
        self.assertEqual(h.events.count("mqtt"), 1)
        self.assertEqual(len(h.mqtt_calls), 1)

    def test_mixed_zoned_and_normal_ordering(self) -> None:
        # a multi-zone appliance followed by a normal one: zone1,zone2,base(0) then normal(0),
        # all loaded BEFORE mqtt (which is last).
        data = [
            {"macAddress": "Z", "applianceTypeName": "AC", "zone": "2"},
            {"macAddress": "N", "applianceTypeName": "WM"},
        ]
        h = _Harness(self, data)
        h.install()
        nh = self._nh_with_api(h)
        _run(nh.setup())
        self.assertEqual(
            [(a.mac_address, a.zone) for a in nh.appliances],
            [("Z", 1), ("Z", 2), ("Z", 0), ("N", 0)],
        )
        self.assertEqual(h.events[0], "load_appliances")
        self.assertEqual(h.events[-1], "mqtt")
        # no load after mqtt
        self.assertEqual(h.events.index("mqtt"), len(h.events) - 1)

    def test_zone_one_not_split(self) -> None:
        data = [{"macAddress": "Z", "applianceTypeName": "AC", "zone": "1"}]
        h = _Harness(self, data)
        h.install()
        nh = self._nh_with_api(h)
        _run(nh.setup())
        self.assertEqual([a.zone for a in nh.appliances], [0])

    def test_empty_mac_skipped(self) -> None:
        data = [
            {"macAddress": "", "applianceTypeName": "GHOST"},
            {"macAddress": "B", "applianceTypeName": "WM"},
        ]
        h = _Harness(self, data)
        h.install()
        nh = self._nh_with_api(h)
        _run(nh.setup())
        self.assertEqual([a.mac_address for a in nh.appliances], ["B"])
        # the appliance without a mac is not loaded
        self.assertNotIn("cmd::0", h.events)

    def test_appliance_load_error_still_appended(self) -> None:
        data = [{"macAddress": "A", "applianceTypeName": "REF"}]
        h = _Harness(self, data, fail_macs={"A"})
        h.install()
        nh = self._nh_with_api(h)
        _run(nh.setup())
        # load_commands raises KeyError but the appliance stays (partial state, like pyhOn)
        self.assertEqual([a.mac_address for a in nh.appliances], ["A"])

    def test_appliance_load_error_redacts_identity_in_log(self) -> None:
        # #19: the except path logs the RAW appliance dict at ERROR (never gated by
        # the debug toggles). MAC/serial must NOT reach the log; non-identity fields
        # (modelName) still do, so the message stays useful for the maintainer.
        data = [{
            "macAddress": "AA:BB:CC:DD:EE:FF",
            "serialNumber": "SN-SECRET-123",
            "applianceTypeName": "REF",
            "modelName": "HDPW5620CNPK",
        }]
        h = _Harness(self, data, fail_macs={"AA:BB:CC:DD:EE:FF"})
        h.install()
        nh = self._nh_with_api(h)
        with self.assertLogs(session_mod._LOGGER, level="ERROR") as cm:
            _run(nh.setup())
        blob = "\n".join(cm.output)
        self.assertNotIn("AA:BB:CC:DD:EE:FF", blob)
        self.assertNotIn("SN-SECRET-123", blob)
        self.assertIn("***", blob)
        self.assertIn("HDPW5620CNPK", blob)  # non-identity survives
        self.assertEqual([a.mac_address for a in nh.appliances], ["AA:BB:CC:DD:EE:FF"])

    def test_mqtt_disabled(self) -> None:
        data = [{"macAddress": "A", "applianceTypeName": "REF"}]
        h = _Harness(self, data)
        h.install()
        nh = self._nh_with_api(h, enable_mqtt=False)
        _run(nh.setup())
        self.assertNotIn("mqtt", h.events)
        self.assertEqual(h.mqtt_calls, [])
        self.assertIsNone(nh._mqtt_client)

    def test_minimal_skips_per_appliance_loads_and_mqtt(self) -> None:
        # #30: config-flow validation builds + counts the appliances but does NOT run
        # the per-appliance load_commands/attributes/statistics, and never starts MQTT.
        data = [
            {"macAddress": "A", "applianceTypeName": "REF"},
            {"macAddress": "B", "applianceTypeName": "WM"},
        ]
        h = _Harness(self, data)
        h.install()
        nh = self._nh_with_api(h, enable_mqtt=False, minimal=True)
        _run(nh.setup())
        # appliances are built (so the flow can count + type them) ...
        self.assertEqual([a.mac_address for a in nh.appliances], ["A", "B"])
        # ... but only load_appliances ran: no per-appliance cmd/attr/stat, no mqtt.
        self.assertEqual(h.events, ["load_appliances"])
        self.assertEqual(h.mqtt_calls, [])
        self.assertIsNone(nh._mqtt_client)
        self.assertEqual(nh._setup_phase, "")  # cleared after a clean setup

    def test_minimal_empty_mac_still_skipped(self) -> None:
        data = [
            {"macAddress": "", "applianceTypeName": "GHOST"},
            {"macAddress": "B", "applianceTypeName": "WM"},
        ]
        h = _Harness(self, data)
        h.install()
        nh = self._nh_with_api(h, enable_mqtt=False, minimal=True)
        _run(nh.setup())
        self.assertEqual([a.mac_address for a in nh.appliances], ["B"])

    def test_create_builds_connection_api_then_setup(self) -> None:
        data = [{"macAddress": "A", "applianceTypeName": "REF"}]
        h = _Harness(self, data)
        h.install()

        created = {}

        class FakeConn:
            def __init__(self, *a, **kw):
                created["args"] = (a, kw)

            async def create(self):
                created["conn_created"] = True
                return self

            async def close(self):
                created["conn_closed"] = True

        def fake_honapi(conn):
            created["api_conn"] = conn
            return h.api

        self._patch(session_mod, "HonConnection", FakeConn)
        self._patch(session_mod, "HonApi", fake_honapi)

        nh = NativeHon("u@x", "p", mobile_id="MID", enable_mqtt=False)
        out = _run(nh.create())
        self.assertIs(out, nh)
        self.assertTrue(created["conn_created"])
        self.assertIsInstance(created["api_conn"], FakeConn)
        self.assertEqual([a.mac_address for a in nh.appliances], ["A"])
        self.assertFalse(h.api.closed)  # success path must NOT close

    def _patch_conn_api_with_failing_setup(self, h):
        # HonConnection.create() succeeds, HonApi is the harness api, but setup()
        # fails (load_appliances raises) so create() must self-clean.
        class FakeConn:
            async def create(self):
                return self

            async def close(self):
                pass

        async def boom():
            raise RuntimeError("setup boom")

        h.api.load_appliances = boom
        self._patch(session_mod, "HonConnection", lambda *a, **k: FakeConn())
        self._patch(session_mod, "HonApi", lambda conn: h.api)

    def test_create_failure_closes_session_no_leak(self) -> None:
        # #31: if setup() raises, create() must close() so the owned ClientSession
        # (via api.close() -> connection.close()) is released, not leaked.
        h = _Harness(self, [])
        h.install()
        self._patch_conn_api_with_failing_setup(h)
        nh = NativeHon("u@x", "p", enable_mqtt=False)
        with self.assertRaises(RuntimeError):
            _run(nh.create())
        self.assertTrue(h.api.closed)  # close() ran on the failed create()

    def test_async_with_create_failure_still_closes(self) -> None:
        # The documented hazard: `async with NativeHon(...)` does NOT run __aexit__
        # when __aenter__/create() raises, so create() itself must clean up.
        h = _Harness(self, [])
        h.install()
        self._patch_conn_api_with_failing_setup(h)

        async def body():
            async with NativeHon("u@x", "p", enable_mqtt=False):
                pass

        with self.assertRaises(RuntimeError):
            _run(body())
        self.assertTrue(h.api.closed)

    def test_create_baseexception_in_setup_still_closes(self) -> None:
        # #31: the guard is `except BaseException` ON PURPOSE so a CANCELLED setup
        # (asyncio.CancelledError is a BaseException, NOT an Exception) also tears
        # down the owned session. `except Exception` would let it leak -> kill that
        # mutant. setup() raises CancelledError here (via load_appliances).
        h = _Harness(self, [])
        h.install()

        class FakeConn:
            async def create(self):
                return self

            async def close(self):
                pass

        async def cancel_boom():
            raise asyncio.CancelledError()

        h.api.load_appliances = cancel_boom
        self._patch(session_mod, "HonConnection", lambda *a, **k: FakeConn())
        self._patch(session_mod, "HonApi", lambda conn: h.api)

        nh = NativeHon("u@x", "p", enable_mqtt=False)
        with self.assertRaises(asyncio.CancelledError):
            _run(nh.create())
        self.assertTrue(h.api.closed)  # close() ran even on a BaseException

    def test_create_failure_in_connection_create_closes_with_no_api(self) -> None:
        # #31: failure point BEFORE _api is set (HonConnection.create() raises).
        # create()'s except still runs close(), which must tolerate _api is None
        # (no AttributeError) AND must close the partially-built connection so its
        # owned ClientSession is not leaked. Exercises the `_api is None` guard in
        # close() on the create() error path + connection cleanup.
        class FakeConn:
            async def create(self):
                raise RuntimeError("connection create boom")

            async def close(self):
                pass

        api_built = {"n": 0}

        def fake_honapi(conn):
            api_built["n"] += 1
            return object()

        self._patch(session_mod, "HonConnection", lambda *a, **k: FakeConn())
        self._patch(session_mod, "HonApi", fake_honapi)

        nh = NativeHon("u@x", "p", enable_mqtt=False)
        with self.assertRaises(RuntimeError):
            _run(nh.create())  # must NOT raise AttributeError from close()
        self.assertEqual(api_built["n"], 0)  # failed before _api was built
        self.assertIsNone(nh._api)

    def test_create_failure_after_mqtt_started_stops_mqtt_and_closes_api(self) -> None:
        # #31: deeper failure point. load_appliances succeeds, MQTT is built, then
        # something AFTER that raises. close() must stop the started MQTT (no leak)
        # AND close the api. Tests the cleanup path with a live _mqtt_client.
        data = [{"macAddress": "A", "applianceTypeName": "REF"}]
        h = _Harness(self, data)
        h.install()

        class FakeConn:
            async def create(self):
                return self

            async def close(self):
                pass

        self._patch(session_mod, "HonConnection", lambda *a, **k: FakeConn())
        self._patch(session_mod, "HonApi", lambda conn: h.api)

        nh = NativeHon("u@x", "p", enable_mqtt=True)

        real_setup = nh.setup

        async def setup_then_boom():
            await real_setup()  # builds appliances + starts MQTT
            assert nh._mqtt_client is h.mqtt_instance
            raise RuntimeError("post-mqtt boom")

        nh.setup = setup_then_boom  # type: ignore[assignment]

        with self.assertRaises(RuntimeError):
            _run(nh.create())
        self.assertTrue(h.mqtt_instance.stopped)  # started MQTT was stopped
        self.assertIsNone(nh._mqtt_client)
        self.assertTrue(h.api.closed)  # api closed too

    def test_create_failure_cleanup_error_does_not_mask_original(self) -> None:
        # #31 (refuter): if close()'s teardown itself raises, it must NOT mask the
        # ORIGINAL setup exception (the config-entry classifier keys off it, e.g. an
        # auth error must surface as ConfigEntryAuthFailed, not be hidden by a
        # cleanup ConnectionResetError). close() is exception-guarded -> original wins.
        h = _Harness(self, [])
        h.install()

        class FakeConn:
            async def create(self):
                return self

            async def close(self):
                pass

        async def setup_boom():
            raise ValueError("ORIGINAL setup error")

        async def close_boom():
            raise RuntimeError("cleanup boom")

        h.api.load_appliances = setup_boom
        h.api.close = close_boom
        self._patch(session_mod, "HonConnection", lambda *a, **k: FakeConn())
        self._patch(session_mod, "HonApi", lambda conn: h.api)

        nh = NativeHon("u@x", "p", enable_mqtt=False)
        with self.assertRaises(ValueError) as ctx:
            _run(nh.create())
        self.assertIn("ORIGINAL", str(ctx.exception))  # cleanup error did not mask it

    def test_close_closes_api(self) -> None:
        h = _Harness(self, [])
        h.install()
        nh = self._nh_with_api(h)
        _run(nh.close())
        self.assertTrue(h.api.closed)

    def test_close_stops_mqtt_then_api(self) -> None:
        # close() stops the MQTT (no leak) and then closes the api; _mqtt_client cleared.
        data = [{"macAddress": "A", "applianceTypeName": "REF"}]
        h = _Harness(self, data)
        h.install()
        nh = self._nh_with_api(h)
        _run(nh.setup())
        self.assertIs(nh._mqtt_client, h.mqtt_instance)
        _run(nh.close())
        self.assertEqual(h.stop_calls, [h.mqtt_instance])
        self.assertTrue(h.mqtt_instance.stopped)
        self.assertIsNone(nh._mqtt_client)
        self.assertTrue(h.api.closed)

    def test_close_without_mqtt_no_stop(self) -> None:
        # enable_mqtt=False: no mqtt -> close() does not stop any client.
        h = _Harness(self, [])
        h.install()
        nh = self._nh_with_api(h, enable_mqtt=False)
        _run(nh.setup())
        _run(nh.close())
        self.assertEqual(h.stop_calls, [])
        self.assertTrue(h.api.closed)

    def test_api_property_raises_before_create(self) -> None:
        nh = NativeHon("u@x", "p")
        with self.assertRaises(NativeAuthError):
            _ = nh.api

    def test_subscribe_and_notify(self) -> None:
        nh = NativeHon("u@x", "p")
        got = []
        nh.subscribe_updates(lambda payload: got.append(payload))
        nh.notify()
        self.assertEqual(got, [None])

    def test_notify_noop_without_subscriber(self) -> None:
        nh = NativeHon("u@x", "p")
        nh.notify()  # must not raise

    def test_satisfies_hon_session_protocol(self) -> None:
        nh = NativeHon("u@x", "p")
        self.assertIsInstance(nh, HonSession)
        # the members that the MQTTClient/integration read (via dir: the `api`
        # property raises if evaluated before create(), which is the right behavior)
        for member in ("api", "appliances", "subscribe_updates", "notify", "close"):
            self.assertIn(member, dir(nh))
        # appliances is readable right away (empty list), api is not (not created)
        self.assertEqual(nh.appliances, [])


if __name__ == "__main__":
    unittest.main()
