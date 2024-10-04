import logging
from datetime import datetime, timedelta

import httpx
from homeassistant.components.recorder.models import (StatisticData,
                                                      StatisticMetaData)
from homeassistant.components.recorder.statistics import \
    _async_import_statistics
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

from . import t, util

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

    first_fetch_complete=False

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
            state_class=data_series_config.state_class,
            icon=data_series_config.icon,
            native_unit_of_measurement=data_series_config.unit_of_measurement,
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
        # On startup we fetch the full history of the data. On subsequent runs we only fetch the
        # last few days (the server default).
        url = self.url
        if not all(entity.first_fetch_complete for entity in self.entities):
            url = util.add_query_to_url(url, {
                'start': '2000-01-01'
            })

        self.logger.warning(f'Fetch history from {url}')
        auth = httpx.BasicAuth(self.username, self.password)
        response = await self.async_client.request('GET', url, auth=auth)
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
            has_sum = entity.entity_description.state_class in (
                SensorStateClass.TOTAL,
                SensorStateClass.TOTAL_INCREASING,
            )
            metadata = StatisticMetaData(
                has_mean=True,
                has_sum=has_sum,
                name=None if entity.name == UNDEFINED else entity.name,
                source=t.DOMAIN,
                statistic_id=statistic_id,
                unit_of_measurement=entity.unit_of_measurement,
            )

            # Group data points by hour so we can calculate the mean
            grouped_data: list[t.GroupedDataPoint] = []
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
                self.create_statistic_data(data_point, has_sum)
                for data_point in grouped_data
            ]

            _async_import_statistics(self.hass, metadata, statistics)

            entity.first_fetch_complete = True


    def create_statistic_data(self, data_point: t.GroupedDataPoint, has_sum: bool) -> StatisticData:
        statistic_data = StatisticData(
            start=data_point['timestamp'],
            state=data_point['last_value'],
            mean=data_point['sum_of_values'] / data_point['num_values']
        )
        if has_sum:
            statistic_data['sum'] = data_point['last_value']
        return statistic_data
