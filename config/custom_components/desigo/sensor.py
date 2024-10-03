import logging
from datetime import datetime, timedelta
from typing import TypedDict

import httpx
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (StatisticData,
                                                      StatisticMetaData)
from homeassistant.components.recorder.statistics import (
    _async_import_statistics, async_add_external_statistics,
    get_last_statistics, statistics_during_period)
from homeassistant.components.sensor import (SensorEntity,
                                             SensorEntityDescription,
                                             SensorStateClass)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.httpx_client import create_async_httpx_client
from homeassistant.helpers.typing import (UNDEFINED, ConfigType,
                                          DiscoveryInfoType, StateType)
from homeassistant.helpers.update_coordinator import (CoordinatorEntity,
                                                      DataUpdateCoordinator)

from . import schema, t

logger = logging.getLogger(__name__)

ICON = 'mdi:heat-pump'
SCAN_INTERVAL = timedelta(minutes=1)

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None=None,
) -> None:
    # This adheres to schema.DOMAIN_SCHEMA, but I don't know how to get the type from a voluptuous
    # schema
    desigo_config = discovery_info
    if desigo_config is None:
        return

    coordinator = DesigoDataUpdateCoordinator(
        hass,
        desigo_config['url'],
        desigo_config['username'],
        desigo_config['password'],
    )

    all_data_series: list[t.DataSeriesConfig] = [
        t.DataSeriesConfig(**data_series)
        for data_series in desigo_config['data_series']
    ]
    entities: list[DesigoCoordinatorEntity] = [
        DesigoCoordinatorEntity(coordinator, data_series)
        for data_series in all_data_series
    ]

    async_add_entities(entities, True)


class DesigoCoordinatorEntity(SensorEntity, CoordinatorEntity['DesigoDataUpdateCoordinator']):  # type: ignore
    data_series_config: t.DataSeriesConfig

    def __init__(
        self,
        coordinator: 'DesigoDataUpdateCoordinator',
        data_series_config: t.DataSeriesConfig,
    ):
        super().__init__(coordinator)
        self.data_series_config = data_series_config
        self.entity_description = SensorEntityDescription(
            key=data_series_config.key,
            name=data_series_config.name,
            device_class=data_series_config.device_class,
            icon=data_series_config.icon,
            native_unit_of_measurement=data_series_config.unit_of_measurement,
            # This makes sense for most data we can get out of Desigo, but it may not apply to
            # all data. If so, we will need to make this configurable + change the logic in
            # DesigoDataUpdateCoordinator._insert_statistics, e.g. to calculate sums instead of
            # means.
            state_class=SensorStateClass.MEASUREMENT,
        )
        self._attr_unique_id = f"{t.DOMAIN}_{self.data_series_config.key}"

        self.coordinator.add_entity(self)


    @property
    def native_value(self) -> StateType:
        return self.coordinator.get_native_value(self)


class DesigoDataUpdateCoordinator(DataUpdateCoordinator[list[t.DataSeries]]):
    async_client: httpx.AsyncClient
    entities: list[DesigoCoordinatorEntity] = []

    url: str
    username: str
    password: str

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        username: str,
        password: str,
    ):
        super().__init__(
            hass,
            logger,
            name=f'Desigo',
            update_interval=timedelta(hours=1)
        )

        self.async_client = create_async_httpx_client(self.hass)
        self.data = []

        self.url = url
        self.username = username
        self.password = password


    def add_entity(self, entity: DesigoCoordinatorEntity) -> None:
        self.entities.append(entity)


    def get_native_value(self, entity: DesigoCoordinatorEntity) -> StateType:
        try:
            data_series = self.get_data_series(entity)
            return data_series.data[-1][1]
        except StopIteration:
            return None


    def get_data_series(
        self,
        entity: DesigoCoordinatorEntity,
        data: list[t.DataSeries] | None=None,
    ) -> t.DataSeries:
        if data is None:
            data = self.data

        return next(
            data_series
            for data_series in data
            if (
                data_series.group == entity.data_series_config.series_group
                and data_series.name == entity.data_series_config.series_name
            )
        )


    async def _async_update_data(self) -> list[t.DataSeries]:
        auth = httpx.BasicAuth(self.username, self.password)
        response = await self.async_client.request('GET', self.url, auth=auth)
        raw_data = response.json()
        data = self.parse_data(raw_data)

        await self._insert_statistics(data)

        return data


    def parse_data(self, raw_data: list) -> list[t.DataSeries]:
        data = [
            self.parse_data_series(raw_data_series)
            for raw_data_series in raw_data
        ]
        return data


    def parse_data_series(self, raw_data_series: dict) -> t.DataSeries:
        data = [
            (datetime.fromisoformat(timestamp), value)
            for timestamp, value in raw_data_series['data']
        ]
        kwargs = {
            **raw_data_series,
            'data': data,
        }
        data_series = t.DataSeries(**kwargs)
        return data_series


    async def _insert_statistics(self, data: list[t.DataSeries]):
        for entity in self.entities:
            # On the first run of this method, our entities do not seem to have entity_ids yet.
            # I'm not sure how to handle this, but it's not a big issue: we will get the same
            # statistics on the next run.
            if not entity.entity_id:
                continue

            try:
                data_series = self.get_data_series(entity, data)
            except StopIteration:
                self.logger.warning(
                    'Failed to find data series "{} - {}" in server response'
                    .format(
                        entity.data_series_config.series_group,
                        entity.data_series_config.series_name,
                    )
                )
                continue

            statistic_id = entity.entity_id
            metadata = StatisticMetaData(
                has_mean=True,
                has_sum=False,
                name=None if entity.name == UNDEFINED else entity.name,
                source=t.DOMAIN,
                statistic_id=statistic_id,
                unit_of_measurement=entity.unit_of_measurement,
            )

            # Group data points by hour so we can calculate the mean
            class GroupedDataPoint(TypedDict):
                timestamp: datetime
                sum_of_values: float
                num_values: int
                last_value: float

            grouped_data: list[GroupedDataPoint] = []
            for timestamp, value in data_series.data:
                truncated_timestamp = timestamp.replace(minute=0, second=0, microsecond=0)
                if len(grouped_data) == 0 or truncated_timestamp != grouped_data[-1]['timestamp']:
                    grouped_data.append({
                        'timestamp': truncated_timestamp,
                        'sum_of_values': 0,
                        'num_values': 0,
                        'last_value': 0,
                    })
                grouped_data[-1]['last_value'] = value
                grouped_data[-1]['num_values'] += 1
                grouped_data[-1]['sum_of_values'] += value

            statistics = [
                StatisticData(
                    start=item['timestamp'],
                    state=item['last_value'],
                    mean=item['sum_of_values'] / item['num_values']
                )
                for item in grouped_data
            ]

            _async_import_statistics(self.hass, metadata, statistics)
