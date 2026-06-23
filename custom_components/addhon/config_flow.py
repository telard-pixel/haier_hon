"""Config flow for Haier hOn Extended."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_ENABLE_DEBUG, CONF_ENABLE_MQTT_DEBUG, DOMAIN
from .error_codes import UNKNOWN, HonErrorCode, classify
from .hon_client import HonClient, _requires_reauth

_LOGGER = logging.getLogger(__name__)


def _error_base_and_code(exc: BaseException, fallback_base: str) -> tuple[str, str]:
    """Map a validation exception to the (form error key, ADDHON-NNN label).

    A code with a localized ``config.error.<slug>`` string (``ui=True``) drives both
    the precise key AND the shown code; otherwise the generic bucket
    (cannot_connect / invalid_auth) is used with the bare code label. A code-less
    exception (legacy string-constructed CannotConnect/InvalidAuth in the tests)
    falls back to the bucket with no code."""
    code = getattr(exc, "error_code", None)
    if isinstance(code, HonErrorCode):
        if code.ui:
            return code.slug, code.label
        return fallback_base, code.label
    return fallback_base, ""


def _redact_email(email: str | None) -> str | None:
    if not email:
        return None
    if "@" not in email:
        return "***"
    _, domain = email.split("@", 1)
    return f"***@{domain}"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("email"): str,
        vol.Required("password"): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the hOn credentials."""
    _LOGGER.debug("ConfigFlow debug: starting validation for account %s", _redact_email(data.get("email")))
    # validation=True: authenticate + count appliances only, NO MQTT and no
    # per-appliance loads, so a slow/blocked realtime or a single dead endpoint can
    # no longer make the whole validation hit the 60s loop cap (issue #30).
    client = HonClient(email=data["email"], password=data["password"], validation=True)

    try:
        try:
            # The client runs synchronous operations in __init__/__aenter__ -> use executor
            _LOGGER.debug("ConfigFlow debug: setup_sync in executor")
            await hass.async_add_executor_job(client.setup_sync)
            await client.async_complete_setup()
            _LOGGER.debug("ConfigFlow debug: client setup completed")
        except ImportError as err:
            code = classify(err)
            _LOGGER.error("Validation failed [%s]: required dependency not installed: %s", code.label, err)
            raise CannotConnect(code) from err
        except Exception as err:
            code = classify(err)
            _LOGGER.error("Validation failed [%s]: %s", code.label, err)
            if _requires_reauth(err):
                raise InvalidAuth(code) from err
            raise CannotConnect(code) from err

        try:
            _LOGGER.debug("ConfigFlow debug: fetching appliances for validation")
            appliances = await client.async_get_appliances()
            _LOGGER.debug(
                "ConfigFlow debug: appliances fetched=%d types=%s",
                len(appliances),
                [
                    str(getattr(appliance, "appliance_type", None)
                        or getattr(appliance, "applianceType", None)
                        or getattr(appliance, "type_name", None)
                        or getattr(appliance, "category", None)
                        or "UNKNOWN").upper()
                    for appliance in appliances
                ],
            )
        except Exception as err:
            code = classify(err)
            _LOGGER.error("Validation failed [%s] fetching appliances: %s", code.label, err)
            if _requires_reauth(err):
                raise InvalidAuth(code) from err
            raise CannotConnect(code) from err
    finally:
        try:
            _LOGGER.debug("ConfigFlow debug: closing client after validation")
            await client.async_close()
        except Exception as err:
            _LOGGER.warning("Error closing HonClient after validation: %s", err)

    return {
        "title": f"Haier hOn ({data['email']})",
        "appliance_count": len(appliances),
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handles the config flow for Haier hOn Extended."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "OptionsFlowHandler":
        """Expose the Options flow (the two debug toggles)."""
        # NB: no @callback here so as not to depend on homeassistant.core.callback
        # (not required for correctness; the test harness does not provide it).
        return OptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the first user step."""
        errors: dict[str, str] = {}
        error_code = ""

        if user_input is not None:
            _LOGGER.debug(
                "ConfigFlow debug: submit user step for account %s",
                _redact_email(user_input.get("email")),
            )
            # Set the unique_id and abort BEFORE the network validation, so re-adding
            # an already-configured account is rejected without a costly hOn login +
            # appliance fetch (rate-limited). Must be OUTSIDE the try below: the
            # AbortFlow raised by _abort_if_unique_id_configured() would otherwise be
            # swallowed by the broad `except Exception`. (#18)
            await self.async_set_unique_id(user_input["email"].lower())
            self._abort_if_unique_id_configured()
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect as err:
                errors["base"], error_code = _error_base_and_code(err, "cannot_connect")
                _LOGGER.debug("ConfigFlow debug: validation failed %s [%s]", errors["base"], error_code)
            except InvalidAuth as err:
                errors["base"], error_code = _error_base_and_code(err, "invalid_auth")
                _LOGGER.debug("ConfigFlow debug: validation failed %s [%s]", errors["base"], error_code)
            except Exception:
                _LOGGER.exception("Unexpected error")
                errors["base"] = "unknown"
                error_code = UNKNOWN.label
            else:
                _LOGGER.debug(
                    "ConfigFlow debug: creating entry for account %s appliance_count=%s",
                    _redact_email(user_input.get("email")),
                    info.get("appliance_count"),
                )
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/tis24dev/addhOn",
                "error_code": error_code,
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Start re-authentication when the hOn token is no longer valid."""
        _LOGGER.debug(
            "ConfigFlow debug: starting reauth for account %s",
            _redact_email(entry_data.get("email")),
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask for the password again (the email stays the entry's one)."""
        errors: dict[str, str] = {}
        error_code = ""
        reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        email = reauth_entry.data["email"]

        if user_input is not None:
            data = {"email": email, "password": user_input["password"]}
            try:
                await validate_input(self.hass, data)
            except CannotConnect as err:
                errors["base"], error_code = _error_base_and_code(err, "cannot_connect")
                _LOGGER.debug("ConfigFlow debug: reauth failed %s [%s]", errors["base"], error_code)
            except InvalidAuth as err:
                errors["base"], error_code = _error_base_and_code(err, "invalid_auth")
                _LOGGER.debug("ConfigFlow debug: reauth failed %s [%s]", errors["base"], error_code)
            except Exception:
                _LOGGER.exception("Unexpected error during reauth")
                errors["base"] = "unknown"
                error_code = UNKNOWN.label
            else:
                # The credentials must belong to the same account: the email is
                # not editable by the user, but we verify the unique_id anyway so
                # as not to re-authenticate an entry with a different account.
                await self.async_set_unique_id(email.lower())
                if reauth_entry.unique_id and self.unique_id != reauth_entry.unique_id:
                    return self.async_abort(reason="reauth_account_mismatch")
                _LOGGER.debug(
                    "ConfigFlow debug: reauth succeeded for %s, updating entry",
                    _redact_email(email),
                )
                return self.async_update_reload_and_abort(reauth_entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("password"): str}),
            errors=errors,
            description_placeholders={"email": email, "error_code": error_code},
        )


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Integration options: two independent debug toggles.

    HA 2024.12.0+: do NOT set self.config_entry in __init__ (deprecated and
    injected automatically). The defaults are read from self.config_entry.options
    (False on installations that never saved options). The values are applied on
    the fly by _apply_debug_options via the options update listener: NB the loggers
    are global to the process, so with more than one account the last one that
    changes wins (typical case = single account).
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_ENABLE_DEBUG: bool(user_input.get(CONF_ENABLE_DEBUG, False)),
                    CONF_ENABLE_MQTT_DEBUG: bool(
                        user_input.get(CONF_ENABLE_MQTT_DEBUG, False)
                    ),
                },
            )

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENABLE_DEBUG,
                        default=options.get(CONF_ENABLE_DEBUG, False),
                    ): bool,
                    vol.Required(
                        CONF_ENABLE_MQTT_DEBUG,
                        default=options.get(CONF_ENABLE_MQTT_DEBUG, False),
                    ): bool,
                }
            ),
        )


class _CodedFlowError(HomeAssistantError):
    """Base for the two flow errors: optionally carries a HonErrorCode.

    Accepts either a HonErrorCode (the new path) or a plain string/None (legacy
    callers and tests). The carried code drives the precise UI key + the shown
    ADDHON-NNN; a string is just the message with no code."""

    def __init__(self, code: HonErrorCode | str | None = None) -> None:
        if isinstance(code, HonErrorCode):
            self.error_code: HonErrorCode | None = code
            super().__init__(str(code))
        else:
            self.error_code = None
            super().__init__("" if code is None else str(code))


class CannotConnect(_CodedFlowError):
    """Connection error."""


class InvalidAuth(_CodedFlowError):
    """Invalid credentials."""
