from homeassistant import config_entries


class StubFlow(config_entries.ConfigFlow, domain="teststub"):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_create_entry(title="Test stub", data={})
