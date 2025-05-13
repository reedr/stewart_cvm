"""Platform for sensor integration."""

import logging

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
    CoverState,
)
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

    async_add_entities([CVMCover(coord)])


class CVMCover(CoverEntity, CVMEntity):
    """Screen as a cover."""

    device_class = CoverDeviceClass.CURTAIN
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, coord: CVMCoordinator) -> None:
        """Get going."""
        super().__init__(coord, "Screen Mask")

    def set_state(self) -> None:
        """Set how things are."""
        status = self.coordinator.device.data["motor_status"]
        self._attr_current_cover_position = self.coordinator.device.data["cover_position"]
        self._attr_is_closing = (status == "EXTENDING")
        self._attr_is_opening = (status == "RETRACTING")
        self._attr_state = CoverState.CLOSED if self.is_closed else CoverState.OPEN
        self._attr_extra_state_attributes = self.coordinator.device.data

    @property
    def current_cover_position(self) -> int:
        """Return scaled position."""
        return self._attr_current_cover_position

    @property
    def is_closed(self) -> bool:
        """Return scaled position."""
        return (self.current_cover_position == 0)

    @property
    def is_open(self) -> bool:
        """Return open."""
        return (self.current_cover_position == 100)

    @property
    def is_closing(self) -> bool:
        """Return scaled position."""
        return self._attr_is_closing

    @property
    def is_opening(self) -> bool:
        """Return scaled position."""
        return self._attr_is_opening

    @property
    def entity_type(self) -> str:
        """Type of entity."""
        return "screen"

    async def async_set_cover_position(self, **kwargs) -> None:
        """Set position."""
        await self.coordinator.device.set_position(int(kwargs.get("position")))

    async def async_open_cover(self, **kwargs) -> None:
        """Open up."""
        await self.coordinator.device.open_mask()

    async def async_close_cover(self, **kwargs) -> None:
        """Close down."""
        await self.coordinator.device.close_mask()

    async def async_stop_cover(self, **kwargs) -> None:
        """Stop cover."""
        await self.coordinator.device.stop_mask()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.set_state()
        self.schedule_update_ha_state()
