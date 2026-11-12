"""Fake Google Home: reports play_media / volume_set over MQTT, plays for 1.5 s."""
import asyncio
import json
from urllib.parse import parse_qs, urlparse

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([FakeSpeaker()])


class FakeSpeaker(MediaPlayerEntity):
    _attr_name = "Living Room speaker"
    _attr_unique_id = "teststub_speaker"
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
    )

    def __init__(self):
        self.entity_id = "media_player.living_room_speaker"
        self._attr_state = MediaPlayerState.OFF
        self._attr_volume_level = 0.25

    async def _report(self, kind, data):
        await self.hass.services.async_call(
            "mqtt", "publish", {"topic": f"test/speaker/{kind}", "payload": json.dumps(data, ensure_ascii=False)}
        )

    async def async_set_volume_level(self, volume):
        self._attr_volume_level = volume
        self.async_write_ha_state()
        await self._report("volume", {"volume": round(volume, 3)})

    async def async_play_media(self, media_type, media_id, **kwargs):
        query = parse_qs(urlparse(media_id).query)
        await self._report("say", {"message": query.get("message", [""])[0], "language": query.get("language", [""])[0], "volume": self._attr_volume_level, "media_id": media_id})
        self._attr_state = MediaPlayerState.PLAYING
        self.async_write_ha_state()

        async def finish():
            await asyncio.sleep(1.5)
            self._attr_state = MediaPlayerState.OFF
            self.async_write_ha_state()

        self.hass.async_create_task(finish())
