"""Home Assistant integration with custom services."""

import logging
from typing import Any, Dict

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.service import async_register_admin_service

from .const import DOMAIN

CVM_CALIBRATE_SERVICE = "calibrate"

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    
    # Register services
    await async_setup_services(hass)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    
    hass.data[DOMAIN].pop(entry.entry_id)
    
    # Remove services if this was the last config entry
    if not hass.data[DOMAIN]:
        async_remove_services(hass)
    
    return True


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for the integration."""
    
    # Register basic service
    hass.services.async_register(
        DOMAIN,
        CVM_CALIBRATE_SERVICE,
        async_handle_calibrate,
        vol.Schema({
            vol.Required("entity_id"): cv.entity_ids,
        })
    )
    
    _LOGGER.info("Services registered for %s", DOMAIN)


@callback
def async_remove_services(hass: HomeAssistant) -> None:
    """Remove services when integration is unloaded."""
    hass.services.async_remove(DOMAIN, CVM_CALIBRATE_SERVICE)
    _LOGGER.info("Services removed for %s", DOMAIN)


async def async_handle_calibrate(call: ServiceCall) -> None:
    """Handle the calibrate service call."""
    hass = call.hass
    entity_ids = call.data["entity_id"]
    
    # Process each entity
    for entity_id in entity_ids:
        # Get the entity from the registry
        entity = hass.states.get(entity_id)
        if entity is None:
            _LOGGER.warning("Entity %s not found", entity_id)
            continue
            
        # Perform action on entity
        await entity.device.calibrate()

