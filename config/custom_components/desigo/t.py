import dataclasses
import sys
from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

if sys.version_info < (3, 11):
    from typing_extensions import NotRequired, TypedDict
else:
    from typing import NotRequired, TypedDict


DOMAIN = 'desigo'


# Keep this in sync with schema.DATA_SERIES_SCHEMA
@dataclasses.dataclass
class DataSeriesConfig:
    name: str
    key: str

    series_group: str
    series_name: str

    device_class: SensorDeviceClass
    state_class: SensorStateClass
    unit_of_measurement: str
    icon: str | None=None



@dataclasses.dataclass
class DataSeries:
    group: str
    name: str
    unit: str
    data: list[tuple[datetime, float]]


class GroupedDataPoint(TypedDict):
    timestamp: datetime
    sum_of_values: float
    num_values: int
    last_value: float
