"""HTTP ingest: one URL per channel, protected by the channel token."""

from __future__ import annotations

import hmac
import json
import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN, MAX_BODY_BYTES
from .ingest import PayloadError, parse_payload, parse_text
from .models import Channel
from .runtime import LogNotifierRuntime

_LOGGER = logging.getLogger(__name__)

INGEST_URL = f"/api/{DOMAIN}/ingest/{{token}}"


def ingest_url(token: str) -> str:
    """The ingest URL of a token (for the config flow and README examples)."""
    return f"/api/{DOMAIN}/ingest/{token}"


class LogNotifierIngestView(HomeAssistantView):
    """Accepts messages from foreign services.

    Deliberately without HA authentication: the token in the path identifies
    and authorizes exactly one channel — just like a Discord webhook. A token
    that leaks therefore only costs that channel, not Home Assistant as a
    whole.
    """

    url = INGEST_URL
    name = f"api:{DOMAIN}:ingest"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _runtime(self) -> LogNotifierRuntime | None:
        entries = self.hass.config_entries.async_entries(DOMAIN)
        for entry in entries:
            runtime = getattr(entry, "runtime_data", None)
            if isinstance(runtime, LogNotifierRuntime):
                return runtime
        return None

    @staticmethod
    def _match_channel(runtime: LogNotifierRuntime, token: str) -> Channel | None:
        """Token → channel, in constant time per candidate."""
        for channel in runtime.channels:
            if channel.token and hmac.compare_digest(channel.token, token):
                return channel
        return None

    async def post(self, request: web.Request, token: str) -> web.Response:
        """Accept a message."""
        runtime = self._runtime()
        if runtime is None:
            return self.json_message("Integration not ready", 503)

        channel = self._match_channel(runtime, token)
        if channel is None or not channel.enabled:
            # No hint about whether the token exists and only the channel is
            # disabled — and the token itself does not belong in the log.
            _LOGGER.warning(
                "Rejected ingest with unknown or disabled token from %s",
                request.remote,
            )
            return self.json_message("Unknown token", 401)

        if not runtime.rate_limiter.allow(channel.id):
            _LOGGER.warning("Channel %s is over the rate limit", channel.id)
            return self.json_message("Too many messages", 429)

        if (
            request.content_length is not None
            and request.content_length > MAX_BODY_BYTES
        ):
            return self.json_message("Message too large", 413)
        raw = await request.content.read(MAX_BODY_BYTES + 1)
        if len(raw) > MAX_BODY_BYTES:
            return self.json_message("Message too large", 413)

        query = request.query
        try:
            body = raw.decode("utf-8")
        except UnicodeDecodeError:
            return self.json_message("Body is not UTF-8", 400)

        content_type = (request.content_type or "").lower()
        try:
            if content_type == "application/json" or body.lstrip().startswith("{"):
                parsed = parse_payload(
                    json.loads(body),
                    default_level=query.get("level"),
                    default_source=query.get("source"),
                )
            else:
                parsed = parse_text(
                    body,
                    default_level=query.get("level"),
                    default_source=query.get("source"),
                    default_title=query.get("title"),
                )
        except json.JSONDecodeError as err:
            return self.json_message(f"Invalid JSON: {err.msg}", 400)
        except PayloadError as err:
            return self.json_message(str(err), 400)

        message = runtime.publish(channel, parsed)
        return self.json(
            {"id": message.id, "channel": channel.id, "level": message.level},
            status_code=202,
        )
