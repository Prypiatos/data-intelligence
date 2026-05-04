import os
from functools import lru_cache

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
