"""Stewart CVM coordinator."""

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .device import CVMDevice

_LOGGER = logging.getLogger(__name__)

type CVMConfigEntry = ConfigEntry[CVMCoordinator]

class CVMCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    def __init__(
        self, hass: HomeAssistant, config_entry: CVMConfigEntry, device: CVMDevice
    ) -> None:
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="CVM Coordinator",
            config_entry=config_entry,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=5),
            # Set always_update to `False` if the data returned from the
            # api can be compared via `__eq__` to avoid duplicate updates
            # being dispatched to listeners
            setup_method = self.async_init,
            update_method = self.async_update,
            always_update=False,
        )
        self._device = device

    @property
    def device(self) -> CVMDevice:
        """The device handle."""
        return self._device

    async def async_init(self):
        """Init the device."""
        await self.device.async_init(self.update_callback)

    async def async_update(self):
        """Fetch data from API endpoint."""
        await self.device.send_query_position()

    @callback
    def update_callback(self, data):
        """Incoming data callback."""
        self.hass.add_job(self.async_set_updated_data, data)

