"""Platform for sensor integration."""

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import CVMConfigEntry, CVMCoordinator
from .entity import CVMEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CVMConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add cover entity."""
    coord = config_entry.runtime_data

    async_add_entities([CVMSelect(coord)])


class CVMSelect(SelectEntity, CVMEntity):
    """Screen aspect selector."""

    def __init__(self, coord: CVMCoordinator) -> None:
        """Get going."""
        super().__init__(coord, "Screen Aspect Ratio")
        self._attr_options = [ar["name"] for ar in self.coordinator.device.data["aspect_ratios"]]
        self._local_current_option = None

    def set_state(self) -> None:
        """Set how things are."""
        self._local_current_option = self.coordinator.device.data["screen_aspect_ratio_string"]

    @property
    def current_option(self) -> str:
        """Override the base class which doesn't work."""
        return self._local_current_option

    async def async_select_option(self, option: str) -> None:
       """Select the ar."""
       _LOGGER.debug("select_option: %s", option)
       self._local_current_option = option
       await self.coordinator.device.set_aspect_ratio(option)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.set_state()
        self.schedule_update_ha_state()
