import os
from functools import lru_cache

from influxdb_client import InfluxDBClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


@lru_cache(maxsize=1)
def get_db_engine() -> Engine:
    url = (
        f"postgresql://{os.getenv('POSTGRES_USER', 'energy_user')}"
        f":{os.getenv('POSTGRES_PASSWORD', 'energy_pass')}"
        f"@{os.getenv('POSTGRES_HOST', 'postgres')}"
        f":{os.getenv('POSTGRES_PORT', '5432')}"
        f"/{os.getenv('POSTGRES_DB', 'energy_db')}"
    )
    return create_engine(url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_influx_client() -> InfluxDBClient:
    return InfluxDBClient(
        url=os.getenv("INFLUXDB_URL", "http://influxdb:8086"),
        token=os.getenv("INFLUXDB_TOKEN", "energy-token-123"),
        org=os.getenv("INFLUXDB_ORG", "energy-org"),
    )
