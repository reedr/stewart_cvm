"""CVM Entity Base class."""

import logging

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import CVMCoordinator
from .device import CVMDevice

_LOGGER = logging.getLogger(__name__)

class CVMEntity(CoordinatorEntity[CVMCoordinator]):
    """Base class."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CVMCoordinator, entity: str) -> None:
        """Set up entity."""
        super().__init__(coordinator, entity)

        self._entity = entity
        self._attr_name = entity
        self._attr_unique_id = f"{self.coordinator.device.device_id}_{self.device_id}"
        _LOGGER.debug("%s", self.unique_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=coordinator.device.device_id
        )

    #        _LOGGER.error(f"new entity={entity} state={state} name={self._attr_name} unique_id={self.unique_id}")

    @property
    def entity_type(self) -> str | None:
        """Type of entity."""
        return None

    @property
    def device_id(self):
        """Return entity id."""
        return self._entity

    @property
    def available(self) -> bool:
        """Return online state."""
        return self.coordinator.device.online

    @property
    def device(self) -> CVMDevice:
        """Return device."""
        return self.coordinator.device
