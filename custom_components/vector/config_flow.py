"""Config flow: add-on discovery via the Supervisor or a manual bridge address."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    SOURCE_HASSIO,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlowWithReload,
    SubentryFlowResult,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_TOKEN
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
import voluptuous as vol

from .api import VectorAuthError, VectorClient, VectorError
from .commands import (
    BEHAVIORS,
    CONF_ANIMATION,
    CONF_BEHAVIOR,
    CONF_RESPONSE,
    CONF_SCRIPT,
    CONF_SENTENCES,
    SUBENTRY_COMMAND,
    split_sentences,
    validate_sentences,
)
from .const import (
    CONF_AGENT,
    CONF_KEEP,
    CONF_LLM_AGENT,
    CONF_RESPOND,
    CONF_TTS_ENGINE,
    CONF_TTS_LANGUAGE,
    CONF_TTS_VOICE,
    CONF_VOICE,
    DEFAULT_AGENT,
    DEFAULT_PORT,
    DOMAIN,
    VOICE_TTS,
    VOICE_WIREPOD,
    default_keep,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_TOKEN, default=""): str,
    }
)


class VectorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a Vector bridge."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> VectorOptionsFlow:
        return VectorOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_COMMAND: VectorCommandFlow}

    async def _validate(self, data: dict[str, Any]) -> str | None:
        client = VectorClient(
            async_get_clientsession(self.hass),
            data[CONF_HOST],
            data[CONF_PORT],
            data.get(CONF_TOKEN),
        )
        try:
            await client.connect()
        except VectorAuthError:
            return "invalid_auth"
        except VectorError:
            return "cannot_connect"
        finally:
            await client.close()
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            if (error := await self._validate(user_input)) is None:
                return self.async_create_entry(
                    title=f"Vector ({user_input[CONF_HOST]})", data=user_input
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        """Vector add-on discovery: host, port and token."""
        config = discovery_info.config
        data = {
            CONF_HOST: config["host"],
            CONF_PORT: int(config["port"]),
            CONF_TOKEN: config.get("token", ""),
        }
        await self.async_set_unique_id(discovery_info.uuid)
        # After a restart the add-on may have a new address or token: update the existing entry.
        self._abort_if_unique_id_configured(updates=data)
        # A reinstalled add-on (e.g. a local copy replaced by the store version) announces
        # itself with a new discovery id: take over the entry it replaces, so devices and
        # entity ids stay.
        for entry in self._async_current_entries(include_ignore=False):
            if entry.source == SOURCE_HASSIO:
                self.hass.config_entries.async_update_entry(
                    entry, unique_id=discovery_info.uuid, data={**entry.data, **data}
                )
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
                return self.async_abort(reason="already_configured")
        self._discovered = data
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if (error := await self._validate(self._discovered)) is None:
                return self.async_create_entry(title="Vector", data=self._discovered)
            errors["base"] = error
        return self.async_show_form(
            step_id="hassio_confirm",
            description_placeholders={"host": self._discovered[CONF_HOST]},
            errors=errors,
        )


class VectorOptionsFlow(OptionsFlowWithReload):
    """Voice → Home Assistant: Assist agent and answers in Vector's voice."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            keep = [p.strip() for p in user_input.get(CONF_KEEP, "").splitlines() if p.strip()]
            if user_input.get(CONF_VOICE) == VOICE_TTS and not user_input.get(CONF_TTS_ENGINE):
                errors[CONF_TTS_ENGINE] = "tts_engine_required"
            else:
                return self.async_create_entry(data={**user_input, CONF_KEEP: keep})
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_AGENT, default=options.get(CONF_AGENT, DEFAULT_AGENT)
                ): selector.ConversationAgentSelector(
                    selector.ConversationAgentSelectorConfig(language=self.hass.config.language)
                ),
                vol.Required(CONF_RESPOND, default=options.get(CONF_RESPOND, True)): bool,
                vol.Optional(
                    CONF_KEEP,
                    default="\n".join(
                        options.get(CONF_KEEP, default_keep(self.hass.config.language))
                    ),
                ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
                vol.Required(
                    CONF_VOICE, default=options.get(CONF_VOICE, VOICE_WIREPOD)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[VOICE_WIREPOD, VOICE_TTS], translation_key=CONF_VOICE
                    )
                ),
                vol.Optional(
                    CONF_TTS_ENGINE, description={"suggested_value": options.get(CONF_TTS_ENGINE)}
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="tts")),
                vol.Optional(
                    CONF_TTS_LANGUAGE,
                    description={"suggested_value": options.get(CONF_TTS_LANGUAGE)},
                ): str,
                vol.Optional(
                    CONF_TTS_VOICE, description={"suggested_value": options.get(CONF_TTS_VOICE)}
                ): str,
                vol.Optional(
                    CONF_LLM_AGENT, description={"suggested_value": options.get(CONF_LLM_AGENT)}
                ): selector.ConversationAgentSelector(
                    selector.ConversationAgentSelectorConfig(language=self.hass.config.language)
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )


NO_BEHAVIOR = "none"


def _command_schema(data: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=data.get(CONF_NAME, "")): str,
            vol.Required(
                CONF_SENTENCES, default="\n".join(data.get(CONF_SENTENCES, []))
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Optional(CONF_RESPONSE, default=data.get(CONF_RESPONSE, "")): str,
            vol.Optional(
                CONF_SCRIPT, description={"suggested_value": data.get(CONF_SCRIPT)}
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="script")),
            vol.Required(
                CONF_BEHAVIOR, default=data.get(CONF_BEHAVIOR) or NO_BEHAVIOR
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[NO_BEHAVIOR, *BEHAVIORS],
                    translation_key=CONF_BEHAVIOR,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_ANIMATION, default=data.get(CONF_ANIMATION, "")): str,
        }
    )


class VectorCommandFlow(ConfigSubentryFlow):
    """Custom voice command: sentences, response, script and robot reaction."""

    async def _form(
        self, step_id: str, user_input: dict[str, Any] | None, current: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, SubentryFlowResult | None]:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**user_input, CONF_SENTENCES: split_sentences(user_input[CONF_SENTENCES])}
            if data.get(CONF_BEHAVIOR) == NO_BEHAVIOR:
                data[CONF_BEHAVIOR] = None
            if error := validate_sentences(data[CONF_SENTENCES], self.hass.config.language):
                errors[CONF_SENTENCES] = error
            else:
                return data, None
            current = data
        return None, self.async_show_form(
            step_id=step_id, data_schema=_command_schema(current), errors=errors
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        data, form = await self._form("user", user_input, {})
        if data is None:
            return form
        return self.async_create_entry(title=data.pop(CONF_NAME), data=data)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        data, form = await self._form(
            "reconfigure", user_input, {**subentry.data, CONF_NAME: subentry.title}
        )
        if data is None:
            return form
        return self.async_update_and_abort(
            self._get_entry(), subentry, title=data.pop(CONF_NAME), data=data
        )
