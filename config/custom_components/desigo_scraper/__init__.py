"""An integration that fetches data from the desigo-scraper project."""

import logging

import voluptuous as vol
from homeassistant import const
from homeassistant.components.sensor import \
    DEVICE_CLASSES_SCHEMA as SENSOR_DEVICE_CLASSES_SCHEMA
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import ConfigType

from . import schema, t

logger = logging.getLogger(__name__)


DOMAIN = t.DOMAIN
CONFIG_SCHEMA = schema.CONFIG_SCHEMA


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    desigo_config = {**config[DOMAIN]}
    hass.data[DOMAIN] = config[DOMAIN]

    await discovery.async_load_platform(
        hass,
        'sensor',
        DOMAIN,
        desigo_config,
        config,
    )

    return True
