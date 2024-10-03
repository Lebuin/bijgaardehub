import voluptuous as vol
from homeassistant import const
from homeassistant.components.sensor import \
    DEVICE_CLASSES_SCHEMA as SENSOR_DEVICE_CLASSES_SCHEMA
from homeassistant.helpers import config_validation as cv

from . import t

# Keep this in sync with t.DataSeries
DATA_SERIES_SCHEMA = vol.Schema({
    vol.Required(const.CONF_NAME): cv.string,
    vol.Required('key'): cv.string,
    vol.Required('series_group'): cv.string,
    vol.Required('series_name'): cv.string,
    vol.Required(const.CONF_DEVICE_CLASS): SENSOR_DEVICE_CLASSES_SCHEMA,
    vol.Optional(const.CONF_ICON): cv.icon,
    vol.Required(const.CONF_UNIT_OF_MEASUREMENT): cv.string,
})


DOMAIN_SCHEMA = vol.Schema({
    vol.Required(const.CONF_URL): cv.url,
    vol.Required(const.CONF_USERNAME): cv.string,
    vol.Required(const.CONF_PASSWORD): cv.string,
    vol.Required('data_series'): [DATA_SERIES_SCHEMA]
})


CONFIG_SCHEMA = vol.Schema({
    t.DOMAIN: DOMAIN_SCHEMA
}, extra=vol.ALLOW_EXTRA)
