import voluptuous as vol
from homeassistant import const
from homeassistant.components import sensor
from homeassistant.helpers import config_validation as cv

from . import t

# Keep this in sync with t.DataSeries
DATA_SERIES_SCHEMA = vol.Schema({
    # The name of the sensor in the UI
    vol.Required(const.CONF_NAME): cv.string,
    # A unique key, use to construct a unique id for the sensor
    vol.Required('key'): cv.string,
    # The name of the group in the desigo-scraper response
    vol.Required('series_group'): cv.string,
    # The name of the series in the desigo-scraper response
    vol.Required('series_name'): cv.string,
    # The device class of the sensor
    vol.Required(const.CONF_DEVICE_CLASS): sensor.DEVICE_CLASSES_SCHEMA,
    # The state class of the sensor statistics
    vol.Required(sensor.CONF_STATE_CLASS): sensor.STATE_CLASSES_SCHEMA,
    # The icon of the sensor
    vol.Optional(const.CONF_ICON): cv.icon,
    # The unit of the sensor measurements
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
