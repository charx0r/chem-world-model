from functools import lru_cache

from sqlalchemy import Engine, create_engine

from chemworldmodel.config import get_settings


@lru_cache(maxsize=1)
def get_sync_engine() -> Engine:
    """Return a singleton sync engine (connection pool is reused across calls)."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        echo=settings.db_echo,
    )
