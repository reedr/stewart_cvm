"""The Stewart CVM integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .const import CVM_PRESETS_ASPECT, CVM_PRESETS_POSITION
from .coordinator import CVMConfigEntry, CVMCoordinator
from .device import CVMDevice

_PLATFORMS: list[Platform] = [Platform.COVER, Platform.SELECT]
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: CVMConfigEntry) -> bool:
    """Set up CVM device from a config entry."""

    aspect_ratios = entry.options.get(CVM_PRESETS_ASPECT, entry.data[CVM_PRESETS_ASPECT])
    motor_positions = entry.options.get(CVM_PRESETS_POSITION, entry.data[CVM_PRESETS_POSITION])
    dev = CVMDevice(
        hass,
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        aspect_ratios,
        motor_positions
    )
    coord = CVMCoordinator(hass, entry, dev)
    entry.runtime_data = coord
    await coord.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True

async def async_update_options(hass: HomeAssistant, entry: CVMConfigEntry) -> bool:
    """Update options."""
    dev = entry.runtime_data.device
    dev.set_aspect_ratios(entry.options.get(CVM_PRESETS_ASPECT, entry.data[CVM_PRESETS_ASPECT]),
                          entry.options.get(CVM_PRESETS_POSITION, entry.data[CVM_PRESETS_POSITION]))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: CVMConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
