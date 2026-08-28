"""The ingest view — the only way into the integration from outside.

The token in the path is the whole authorization, so what is tested here is not
only the happy path but what happens with a wrong, disabled or missing one.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.lognotifier.const import (
    CONF_CHANNELS,
    LEVEL_ERROR,
    LEVEL_INFO,
    LEVEL_WARNING,
    MAX_BODY_BYTES,
    RATE_LIMIT_BURST,
)

from .conftest import BACKUP_TOKEN, channel_options

URL = f"/api/lognotifier/ingest/{BACKUP_TOKEN}"


async def test_json_message_is_accepted(
    hass: HomeAssistant, setup_entry, hass_client_no_auth
) -> None:
    """A JSON body ends up in the store with its fields."""
    client = await hass_client_no_auth()

    response = await client.post(
        URL,
        json={
            "content": "Backup failed",
            "level": "ERROR",
            "title": "nightly",
            "source": "borg",
            "tags": ["backup", "nightly"],
        },
    )

    assert response.status == 202
    body = await response.json()
    assert body["channel"] == "backups"
    assert body["level"] == LEVEL_ERROR

    messages = setup_entry.runtime_data.store.messages("backups")
    assert len(messages) == 1
    assert messages[0].content == "Backup failed"
    assert messages[0].title == "nightly"
    assert messages[0].source == "borg"
    assert messages[0].tags == ["backup", "nightly"]


async def test_plain_text_takes_level_and_source_from_the_query(
    hass: HomeAssistant, setup_entry, hass_client_no_auth
) -> None:
    """The plain-text route is the one a shell script uses."""
    client = await hass_client_no_auth()

    response = await client.post(
        f"{URL}?level=WARNING&source=cron&title=disk",
        data="disk almost full",
        headers={"Content-Type": "text/plain"},
    )

    assert response.status == 202
    message = setup_entry.runtime_data.store.messages("backups")[0]
    assert message.level == LEVEL_WARNING
    assert message.source == "cron"
    assert message.title == "disk"
    assert message.content == "disk almost full"


async def test_body_without_content_type_is_read_as_json_when_it_looks_like_it(
    hass: HomeAssistant, setup_entry, hass_client_no_auth
) -> None:
    """`curl -d '{"content": …}'` sends form-urlencoded; the body decides."""
    client = await hass_client_no_auth()

    response = await client.post(URL, data='{"content": "from curl"}')

    assert response.status == 202
    assert setup_entry.runtime_data.store.messages("backups")[0].content == "from curl"


async def test_unknown_token_is_rejected(
    hass: HomeAssistant, setup_entry, hass_client_no_auth
) -> None:
    """An unknown token gets 401 — and nothing is stored."""
    client = await hass_client_no_auth()

    response = await client.post(
        "/api/lognotifier/ingest/nope", json={"content": "hello"}
    )

    assert response.status == 401
    assert setup_entry.runtime_data.store.messages("backups") == []


@pytest.mark.parametrize(
    "entry_options",
    [{CONF_CHANNELS: channel_options(enabled=False)}],
)
async def test_disabled_channel_is_rejected_like_an_unknown_one(
    hass: HomeAssistant, setup_entry, hass_client_no_auth
) -> None:
    """A disabled channel must not be distinguishable from a wrong token.

    Otherwise the response tells an attacker that the token is valid.
    """
    client = await hass_client_no_auth()

    response = await client.post(URL, json={"content": "hello"})

    assert response.status == 401
    assert await response.json() == {"message": "Unknown token"}


async def test_invalid_json_is_reported(
    hass: HomeAssistant, setup_entry, hass_client_no_auth
) -> None:
    """A broken body is a client error, not a 500."""
    client = await hass_client_no_auth()

    response = await client.post(
        URL, data="{not json", headers={"Content-Type": "application/json"}
    )

    assert response.status == 400
    assert "Invalid JSON" in (await response.json())["message"]


async def test_json_without_content_is_reported(
    hass: HomeAssistant, setup_entry, hass_client_no_auth
) -> None:
    """`content` is the one field a message cannot do without."""
    client = await hass_client_no_auth()

    response = await client.post(URL, json={"level": "INFO"})

    assert response.status == 400


async def test_oversized_body_is_refused(
    hass: HomeAssistant, setup_entry, hass_client_no_auth
) -> None:
    """The limit protects the store, so it is enforced before parsing."""
    client = await hass_client_no_auth()

    response = await client.post(URL, data="x" * (MAX_BODY_BYTES + 100))

    assert response.status == 413
    assert setup_entry.runtime_data.store.messages("backups") == []


async def test_rate_limit_answers_429_after_the_burst(
    hass: HomeAssistant, setup_entry, hass_client_no_auth
) -> None:
    """A runaway service must not be able to fill the store."""
    client = await hass_client_no_auth()

    accepted = 0
    for index in range(RATE_LIMIT_BURST + 5):
        response = await client.post(URL, json={"content": f"message {index}"})
        if response.status == 202:
            accepted += 1
        else:
            assert response.status == 429
            break

    assert accepted <= RATE_LIMIT_BURST
    assert accepted > 0


async def test_default_level_is_info(
    hass: HomeAssistant, setup_entry, hass_client_no_auth
) -> None:
    """A message without a level is INFO, not something unspecified."""
    client = await hass_client_no_auth()

    await client.post(URL, json={"content": "just so you know"})

    assert setup_entry.runtime_data.store.messages("backups")[0].level == LEVEL_INFO
