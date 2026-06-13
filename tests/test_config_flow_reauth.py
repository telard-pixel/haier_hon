"""Tests for the reauth config flow (commit "add reauth flow for expired hOn
credentials").

Covers: async_step_reauth forwards to a password-only reauth_confirm form
(email taken from the entry), a successful reauth updates only the password and
aborts with reauth_successful, validate_input errors map to the form, and the
account-match guard aborts with reauth_account_mismatch.

Uses stdlib unittest with HA + voluptuous stubs, so no real HA install needed.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _mod(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    return module


def _install_stubs() -> None:
    ha = _mod("homeassistant")

    config_entries = _mod("homeassistant.config_entries")
    config_entries.ConfigEntry = getattr(
        config_entries, "ConfigEntry", type("ConfigEntry", (), {})
    )

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    config_entries.ConfigFlow = getattr(config_entries, "ConfigFlow", ConfigFlow)

    core = _mod("homeassistant.core")
    core.HomeAssistant = getattr(core, "HomeAssistant", type("HomeAssistant", (), {}))

    data_entry_flow = _mod("homeassistant.data_entry_flow")
    data_entry_flow.FlowResult = getattr(data_entry_flow, "FlowResult", dict)

    exceptions = _mod("homeassistant.exceptions")
    base_err = getattr(exceptions, "HomeAssistantError", type("HomeAssistantError", (Exception,), {}))
    exceptions.HomeAssistantError = base_err
    exceptions.ConfigEntryNotReady = getattr(
        exceptions, "ConfigEntryNotReady", type("ConfigEntryNotReady", (base_err,), {})
    )
    exceptions.ConfigEntryAuthFailed = getattr(
        exceptions, "ConfigEntryAuthFailed", type("ConfigEntryAuthFailed", (base_err,), {})
    )

    helpers = _mod("homeassistant.helpers")
    update_coordinator = _mod("homeassistant.helpers.update_coordinator")
    update_coordinator.DataUpdateCoordinator = getattr(
        update_coordinator, "DataUpdateCoordinator", type("DataUpdateCoordinator", (), {})
    )
    update_coordinator.UpdateFailed = getattr(
        update_coordinator, "UpdateFailed", type("UpdateFailed", (Exception,), {})
    )

    ha.config_entries = config_entries
    ha.core = core
    ha.exceptions = exceptions
    ha.helpers = helpers
    helpers.update_coordinator = update_coordinator

    if "voluptuous" not in sys.modules:
        vol = _mod("voluptuous")
        vol.Schema = lambda schema=None, **kwargs: schema

        class Required:
            def __init__(self, key, *args, **kwargs):
                self.key = key

        vol.Required = Required


_install_stubs()


class _FakeEntry:
    def __init__(self, email="person@example.com", unique_id="person@example.com", password="old"):
        self.entry_id = "entry-1"
        self.data = {"email": email, "password": password}
        self.unique_id = unique_id


class _FakeConfigEntries:
    def __init__(self, entry):
        self._entry = entry

    def async_get_entry(self, entry_id):
        return self._entry


class _FakeHass:
    def __init__(self, entry):
        self.config_entries = _FakeConfigEntries(entry)


def _make_flow(entry):
    """Build a real ConfigFlow with the HA-provided helpers stubbed to capture."""
    from custom_components.haier_hon.config_flow import ConfigFlow

    flow = ConfigFlow()
    flow.hass = _FakeHass(entry)
    flow.context = {"source": "reauth", "entry_id": entry.entry_id}
    flow.unique_id = None
    flow.calls = {}

    async def _set_unique_id(unique_id):
        flow.unique_id = unique_id

    def _show_form(*, step_id, data_schema=None, errors=None, description_placeholders=None):
        return {
            "type": "form",
            "step_id": step_id,
            "errors": errors or {},
            "description_placeholders": description_placeholders or {},
        }

    def _abort(*, reason):
        return {"type": "abort", "reason": reason}

    def _update_reload_and_abort(target_entry, *, data=None, **kwargs):
        flow.calls["update"] = {"entry": target_entry, "data": data}
        return {"type": "abort", "reason": "reauth_successful", "data": data}

    flow.async_set_unique_id = _set_unique_id
    flow.async_show_form = _show_form
    flow.async_abort = _abort
    flow.async_update_reload_and_abort = _update_reload_and_abort
    return flow


class ReauthFlowTest(unittest.IsolatedAsyncioTestCase):
    def _patch_validate(self, fn) -> None:
        from custom_components.haier_hon import config_flow

        original = config_flow.validate_input
        config_flow.validate_input = fn
        self.addCleanup(setattr, config_flow, "validate_input", original)

    async def test_reauth_shows_password_form_with_email_placeholder(self) -> None:
        entry = _FakeEntry()
        flow = _make_flow(entry)

        result = await flow.async_step_reauth(entry.data)

        self.assertEqual("form", result["type"])
        self.assertEqual("reauth_confirm", result["step_id"])
        self.assertEqual("person@example.com", result["description_placeholders"]["email"])

    async def test_reauth_success_updates_only_password(self) -> None:
        seen = {}

        async def ok(hass, data):
            seen.update(data)
            return {"title": "x", "appliance_count": 1}

        self._patch_validate(ok)
        flow = _make_flow(_FakeEntry())

        result = await flow.async_step_reauth_confirm({"password": "new-pass"})

        self.assertEqual("abort", result["type"])
        self.assertEqual("reauth_successful", result["reason"])
        # validate_input got the existing email + the new password
        self.assertEqual({"email": "person@example.com", "password": "new-pass"}, seen)
        # the entry is updated keeping the email, changing the password
        self.assertEqual(
            {"email": "person@example.com", "password": "new-pass"},
            flow.calls["update"]["data"],
        )

    async def test_reauth_invalid_auth_reshows_form(self) -> None:
        from custom_components.haier_hon.config_flow import InvalidAuth

        async def bad(hass, data):
            raise InvalidAuth("nope")

        self._patch_validate(bad)
        flow = _make_flow(_FakeEntry())

        result = await flow.async_step_reauth_confirm({"password": "x"})

        self.assertEqual("form", result["type"])
        self.assertEqual("invalid_auth", result["errors"]["base"])
        self.assertNotIn("update", flow.calls)

    async def test_reauth_cannot_connect_reshows_form(self) -> None:
        from custom_components.haier_hon.config_flow import CannotConnect

        async def down(hass, data):
            raise CannotConnect("offline")

        self._patch_validate(down)
        flow = _make_flow(_FakeEntry())

        result = await flow.async_step_reauth_confirm({"password": "x"})

        self.assertEqual("form", result["type"])
        self.assertEqual("cannot_connect", result["errors"]["base"])

    async def test_reauth_unexpected_error_maps_to_unknown(self) -> None:
        from custom_components.haier_hon import config_flow

        async def boom(hass, data):
            raise RuntimeError("weird")

        self._patch_validate(boom)
        flow = _make_flow(_FakeEntry())

        with self.assertLogs(config_flow._LOGGER.name, level="ERROR"):
            result = await flow.async_step_reauth_confirm({"password": "x"})

        self.assertEqual("unknown", result["errors"]["base"])

    async def test_reauth_aborts_on_account_mismatch(self) -> None:
        async def ok(hass, data):
            return {"title": "x", "appliance_count": 0}

        self._patch_validate(ok)
        # entry's unique_id differs from the email-derived unique_id -> mismatch
        entry = _FakeEntry(email="person@example.com", unique_id="other@example.com")
        flow = _make_flow(entry)

        result = await flow.async_step_reauth_confirm({"password": "x"})

        self.assertEqual("abort", result["type"])
        self.assertEqual("reauth_account_mismatch", result["reason"])
        self.assertNotIn("update", flow.calls)


if __name__ == "__main__":
    unittest.main()
