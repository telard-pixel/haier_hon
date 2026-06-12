"""Regression tests for command failures surfacing to Home Assistant."""
from __future__ import annotations

import asyncio
import concurrent.futures
import enum
import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _ensure_module(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    return module


def _install_homeassistant_stubs() -> None:
    homeassistant = _ensure_module("homeassistant")

    config_entries = _ensure_module("homeassistant.config_entries")

    class ConfigEntry:
        pass

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    config_entries.ConfigEntry = getattr(config_entries, "ConfigEntry", ConfigEntry)
    config_entries.ConfigFlow = getattr(config_entries, "ConfigFlow", ConfigFlow)

    core = _ensure_module("homeassistant.core")

    class HomeAssistant:
        pass

    core.HomeAssistant = getattr(core, "HomeAssistant", HomeAssistant)

    exceptions = _ensure_module("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        pass

    class ConfigEntryNotReady(HomeAssistantError):
        pass

    class ConfigEntryAuthFailed(HomeAssistantError):
        pass

    exceptions.HomeAssistantError = getattr(exceptions, "HomeAssistantError", HomeAssistantError)
    exceptions.ConfigEntryNotReady = getattr(
        exceptions, "ConfigEntryNotReady", ConfigEntryNotReady
    )
    exceptions.ConfigEntryAuthFailed = getattr(
        exceptions, "ConfigEntryAuthFailed", ConfigEntryAuthFailed
    )

    helpers = _ensure_module("homeassistant.helpers")
    entity = _ensure_module("homeassistant.helpers.entity")
    entity.DeviceInfo = getattr(entity, "DeviceInfo", dict)

    entity_platform = _ensure_module("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = getattr(
        entity_platform, "AddEntitiesCallback", object
    )

    update_coordinator = _ensure_module("homeassistant.helpers.update_coordinator")

    class CoordinatorEntity:
        def __init__(self, coordinator) -> None:
            self.coordinator = coordinator
            self.hass = getattr(coordinator, "hass", None)

    class DataUpdateCoordinator:
        pass

    class UpdateFailed(Exception):
        pass

    update_coordinator.CoordinatorEntity = getattr(
        update_coordinator, "CoordinatorEntity", CoordinatorEntity
    )
    update_coordinator.DataUpdateCoordinator = getattr(
        update_coordinator, "DataUpdateCoordinator", DataUpdateCoordinator
    )
    update_coordinator.UpdateFailed = getattr(update_coordinator, "UpdateFailed", UpdateFailed)

    components = _ensure_module("homeassistant.components")
    switch_module = _ensure_module("homeassistant.components.switch")
    select_module = _ensure_module("homeassistant.components.select")
    climate_module = _ensure_module("homeassistant.components.climate")
    climate_const = _ensure_module("homeassistant.components.climate.const")

    class SwitchEntity:
        pass

    class SelectEntity:
        pass

    class ClimateEntity:
        pass

    class ClimateEntityFeature(enum.IntFlag):
        TARGET_TEMPERATURE = 1
        FAN_MODE = 2
        TURN_ON = 4
        TURN_OFF = 8

    class HVACMode(str, enum.Enum):
        OFF = "off"
        AUTO = "auto"
        COOL = "cool"
        DRY = "dry"
        HEAT = "heat"
        FAN_ONLY = "fan_only"

    switch_module.SwitchEntity = getattr(switch_module, "SwitchEntity", SwitchEntity)
    select_module.SelectEntity = getattr(select_module, "SelectEntity", SelectEntity)
    climate_module.ClimateEntity = getattr(climate_module, "ClimateEntity", ClimateEntity)
    climate_const.ClimateEntityFeature = getattr(
        climate_const, "ClimateEntityFeature", ClimateEntityFeature
    )
    climate_const.HVACMode = getattr(climate_const, "HVACMode", HVACMode)

    homeassistant.config_entries = config_entries
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    homeassistant.helpers = helpers
    homeassistant.components = components
    helpers.entity = entity
    helpers.entity_platform = entity_platform
    helpers.update_coordinator = update_coordinator
    components.switch = switch_module
    components.select = select_module
    components.climate = climate_module
    climate_module.const = climate_const


_install_homeassistant_stubs()


class FakeClient:
    def run_command_sync(self, coro) -> None:
        asyncio.run(coro)


class FakeCoordinator:
    def __init__(
        self,
        data: dict,
        refresh_failure: Exception | None = None,
        request_refresh_skips: bool = False,
    ) -> None:
        self.data = data
        self.hass = None
        self.refreshes = 0
        self.direct_refreshes = 0
        self.request_refreshes = 0
        self.last_update_success = True
        self.last_exception = None
        self._refresh_failure = refresh_failure
        self._request_refresh_skips = request_refresh_skips

    async def _finish_refresh(self) -> None:
        self.refreshes += 1
        if self._refresh_failure is not None:
            self.last_update_success = False
            self.last_exception = self._refresh_failure

    async def async_refresh(self) -> None:
        self.direct_refreshes += 1
        await self._finish_refresh()

    async def async_request_refresh(self) -> None:
        self.request_refreshes += 1
        if not self._request_refresh_skips:
            await self._finish_refresh()


class FakeHass:
    async def async_add_executor_job(self, func, *args):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(func, *args).result(timeout=5)


class Param:
    def __init__(self, value=None, values=None) -> None:
        self.value = value
        self.values = values


class RejectingParam:
    def __init__(self, value=None) -> None:
        self._value = value

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value) -> None:
        raise RuntimeError("setter rejected value")


class MutatingRejectingParam:
    def __init__(self, value=None) -> None:
        self._value = value
        self.reject_next = True

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value) -> None:
        self._value = value
        if self.reject_next:
            self.reject_next = False
            raise RuntimeError("setter mutated then rejected value")


class FailingCommand:
    def __init__(self, parameters=None) -> None:
        self.parameters = parameters or {}
        self.send_calls = 0

    async def send(self) -> None:
        self.send_calls += 1
        raise RuntimeError("device rejected command")


class RecordingCommand:
    def __init__(self, parameters=None) -> None:
        self.parameters = parameters or {}
        self.send_calls = 0

    async def send(self) -> None:
        self.send_calls += 1


class CommandFailureTest(unittest.IsolatedAsyncioTestCase):
    def _attach(self, entity) -> None:
        entity.hass = FakeHass()

    async def test_switch_command_failure_raises_service_error(self) -> None:
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.haier_hon.switch import HonWashingMachineSwitch

        command = FailingCommand()
        coordinator = FakeCoordinator(
            {
                "washer-1": {
                    "type": "WM",
                    "name": "Washer",
                    "appliance": types.SimpleNamespace(commands={"startProgram": command}),
                    "attributes": {},
                    "settings": {},
                }
            }
        )
        entity = HonWashingMachineSwitch(coordinator, "washer-1", FakeClient())
        self._attach(entity)

        with self.assertRaisesRegex(HomeAssistantError, "device rejected command"):
            await entity.async_turn_on()

        self.assertEqual(1, command.send_calls)
        self.assertEqual(0, coordinator.refreshes)

    async def test_select_command_failure_raises_service_error(self) -> None:
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.haier_hon.select import HonProgramSelect

        command = FailingCommand(
            {"program": Param(values={"1": "Cotone"})}
        )
        coordinator = FakeCoordinator(
            {
                "washer-1": {
                    "type": "WM",
                    "name": "Washer",
                    "appliance": types.SimpleNamespace(commands={"startProgram": command}),
                    "attributes": {},
                    "settings": {},
                }
            }
        )
        entity = HonProgramSelect(coordinator, "washer-1", FakeClient())
        self._attach(entity)

        with self.assertRaisesRegex(HomeAssistantError, "device rejected command"):
            await entity.async_select_option("Sintetici")

        self.assertEqual(1, command.send_calls)
        self.assertEqual(0, coordinator.refreshes)

    async def test_climate_command_failure_raises_service_error(self) -> None:
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.haier_hon.climate import HaierClimateEntity

        command = FailingCommand({"tempSel": Param()})
        coordinator = FakeCoordinator(
            {
                "ac-1": {
                    "type": "AC",
                    "name": "AC",
                    "appliance": types.SimpleNamespace(commands={"settings": command}),
                    "attributes": {},
                    "settings": {},
                }
            }
        )
        entity = HaierClimateEntity(coordinator, "ac-1", FakeClient())
        self._attach(entity)

        with self.assertRaisesRegex(HomeAssistantError, "device rejected command"):
            await entity.async_set_temperature(temperature=22)

        self.assertEqual(1, command.send_calls)
        self.assertEqual(0, coordinator.refreshes)

    async def test_switch_refresh_failure_after_send_raises_service_error(self) -> None:
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.haier_hon.switch import HonWashingMachineSwitch

        command = RecordingCommand()
        coordinator = FakeCoordinator(
            {
                "washer-1": {
                    "type": "WM",
                    "name": "Washer",
                    "appliance": types.SimpleNamespace(commands={"startProgram": command}),
                    "attributes": {},
                    "settings": {},
                }
            },
            refresh_failure=RuntimeError("refresh failed after command"),
            request_refresh_skips=True,
        )
        entity = HonWashingMachineSwitch(coordinator, "washer-1", FakeClient())
        self._attach(entity)

        with self.assertRaisesRegex(HomeAssistantError, "refresh failed after command"):
            await entity.async_turn_on()

        self.assertEqual(1, command.send_calls)
        self.assertEqual(1, coordinator.refreshes)
        self.assertEqual(1, coordinator.direct_refreshes)
        self.assertEqual(0, coordinator.request_refreshes)

    async def test_select_refresh_failure_after_send_raises_service_error(self) -> None:
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.haier_hon.select import HonProgramSelect

        command = RecordingCommand({"program": Param(values={"1": "Cotone"})})
        coordinator = FakeCoordinator(
            {
                "washer-1": {
                    "type": "WM",
                    "name": "Washer",
                    "appliance": types.SimpleNamespace(commands={"startProgram": command}),
                    "attributes": {},
                    "settings": {},
                }
            },
            refresh_failure=RuntimeError("refresh failed after command"),
            request_refresh_skips=True,
        )
        entity = HonProgramSelect(coordinator, "washer-1", FakeClient())
        self._attach(entity)

        with self.assertRaisesRegex(HomeAssistantError, "refresh failed after command"):
            await entity.async_select_option("Sintetici")

        self.assertEqual(1, command.send_calls)
        self.assertEqual(1, coordinator.refreshes)
        self.assertEqual(1, coordinator.direct_refreshes)
        self.assertEqual(0, coordinator.request_refreshes)

    async def test_climate_refresh_failure_after_send_raises_service_error(self) -> None:
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.haier_hon.climate import HaierClimateEntity

        command = RecordingCommand({"tempSel": Param()})
        coordinator = FakeCoordinator(
            {
                "ac-1": {
                    "type": "AC",
                    "name": "AC",
                    "appliance": types.SimpleNamespace(commands={"settings": command}),
                    "attributes": {},
                    "settings": {},
                }
            },
            refresh_failure=RuntimeError("refresh failed after command"),
            request_refresh_skips=True,
        )
        entity = HaierClimateEntity(coordinator, "ac-1", FakeClient())
        self._attach(entity)

        with self.assertRaisesRegex(HomeAssistantError, "refresh failed after command"):
            await entity.async_set_temperature(temperature=22)

        self.assertEqual(1, command.send_calls)
        self.assertEqual(1, coordinator.refreshes)
        self.assertEqual(1, coordinator.direct_refreshes)
        self.assertEqual(0, coordinator.request_refreshes)

    async def test_climate_missing_temperature_parameter_raises_before_send(self) -> None:
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.haier_hon.climate import HaierClimateEntity

        command = RecordingCommand({})
        coordinator = FakeCoordinator(
            {
                "ac-1": {
                    "type": "AC",
                    "name": "AC",
                    "appliance": types.SimpleNamespace(commands={"settings": command}),
                    "attributes": {},
                    "settings": {},
                }
            }
        )
        entity = HaierClimateEntity(coordinator, "ac-1", FakeClient())
        self._attach(entity)

        with self.assertRaisesRegex(HomeAssistantError, "tempSel"):
            await entity.async_set_temperature(temperature=22)

        self.assertEqual(0, command.send_calls)
        self.assertEqual(0, coordinator.refreshes)

    async def test_climate_missing_hvac_parameter_raises_before_send(self) -> None:
        from homeassistant.components.climate.const import HVACMode
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.haier_hon.climate import HaierClimateEntity

        command = RecordingCommand({"onOffStatus": Param("0")})
        coordinator = FakeCoordinator(
            {
                "ac-1": {
                    "type": "AC",
                    "name": "AC",
                    "appliance": types.SimpleNamespace(commands={"settings": command}),
                    "attributes": {},
                    "settings": {},
                }
            }
        )
        entity = HaierClimateEntity(coordinator, "ac-1", FakeClient())
        self._attach(entity)

        with self.assertRaisesRegex(HomeAssistantError, "machMode"):
            await entity.async_set_hvac_mode(HVACMode.COOL)

        self.assertEqual(0, command.send_calls)
        self.assertEqual("0", command.parameters["onOffStatus"].value)
        self.assertEqual(0, coordinator.refreshes)

    async def test_climate_hvac_setter_failure_rolls_back_previous_params(self) -> None:
        from homeassistant.components.climate.const import HVACMode
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.haier_hon.climate import HaierClimateEntity

        command = RecordingCommand(
            {"onOffStatus": Param("0"), "machMode": RejectingParam("1")}
        )
        coordinator = FakeCoordinator(
            {
                "ac-1": {
                    "type": "AC",
                    "name": "AC",
                    "appliance": types.SimpleNamespace(commands={"settings": command}),
                    "attributes": {},
                    "settings": {},
                }
            }
        )
        entity = HaierClimateEntity(coordinator, "ac-1", FakeClient())
        self._attach(entity)

        with self.assertRaisesRegex(HomeAssistantError, "setter rejected value"):
            await entity.async_set_hvac_mode(HVACMode.COOL)

        self.assertEqual(0, command.send_calls)
        self.assertEqual("0", command.parameters["onOffStatus"].value)
        self.assertEqual(0, coordinator.refreshes)

    async def test_climate_hvac_mutating_setter_failure_rolls_back_current_param(self) -> None:
        from homeassistant.components.climate.const import HVACMode
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.haier_hon.climate import HaierClimateEntity

        command = RecordingCommand(
            {"onOffStatus": Param("0"), "machMode": MutatingRejectingParam("1")}
        )
        coordinator = FakeCoordinator(
            {
                "ac-1": {
                    "type": "AC",
                    "name": "AC",
                    "appliance": types.SimpleNamespace(commands={"settings": command}),
                    "attributes": {},
                    "settings": {},
                }
            }
        )
        entity = HaierClimateEntity(coordinator, "ac-1", FakeClient())
        self._attach(entity)

        with self.assertRaisesRegex(HomeAssistantError, "mutated then rejected"):
            await entity.async_set_hvac_mode(HVACMode.COOL)

        self.assertEqual(0, command.send_calls)
        self.assertEqual("0", command.parameters["onOffStatus"].value)
        self.assertEqual("1", command.parameters["machMode"].value)
        self.assertEqual(0, coordinator.refreshes)

    async def test_climate_missing_fan_parameter_raises_before_send(self) -> None:
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.haier_hon.climate import HaierClimateEntity

        command = RecordingCommand({})
        coordinator = FakeCoordinator(
            {
                "ac-1": {
                    "type": "AC",
                    "name": "AC",
                    "appliance": types.SimpleNamespace(commands={"settings": command}),
                    "attributes": {},
                    "settings": {},
                }
            }
        )
        entity = HaierClimateEntity(coordinator, "ac-1", FakeClient())
        self._attach(entity)

        with self.assertRaisesRegex(HomeAssistantError, "windSpeed"):
            await entity.async_set_fan_mode("auto")

        self.assertEqual(0, command.send_calls)
        self.assertEqual(0, coordinator.refreshes)


if __name__ == "__main__":
    unittest.main()
