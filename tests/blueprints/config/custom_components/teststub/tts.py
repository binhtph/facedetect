from homeassistant.components.tts import TextToSpeechEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([StubTTS()])


class StubTTS(TextToSpeechEntity):
    _attr_name = "Stub TTS"
    _attr_unique_id = "teststub_tts"

    def __init__(self):
        self.entity_id = "tts.stub"

    @property
    def default_language(self):
        return "en"

    @property
    def supported_languages(self):
        return ["en", "vi"]

    def get_tts_audio(self, message, language, options):
        return "mp3", b"ID3stub"
