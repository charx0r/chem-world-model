"""Shared test fixtures for ChemWorldModel."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from chemworldmodel.db.engine import get_sync_engine


@pytest.fixture(scope="session")
def engine() -> Engine:
    """Create a sync engine for testing (uses DATABASE_URL from env/.env)."""
    return get_sync_engine()


@pytest.fixture()
def connection(engine: Engine):
    """Provide a connection that rolls back after each test."""
    with engine.connect() as conn:
        trans = conn.begin()
        yield conn
        trans.rollback()
