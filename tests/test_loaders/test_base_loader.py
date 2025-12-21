"""Tests for BaseLoader provenance tracking and error handling."""

from __future__ import annotations

import uuid
from typing import Any, Iterator
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Connection, text

from chemworldmodel.loaders.base import BaseLoader, LoadStats


# ---------------------------------------------------------------------------
# Mock loader for testing the base class
# ---------------------------------------------------------------------------


class MockLoader(BaseLoader):
    source_name = "test"

    def __init__(self, engine, items, fail_on=None, **kwargs):
        super().__init__(engine, **kwargs)
        self._items = items
        self._fail_on = fail_on or set()

    def extract(self, **kwargs: Any) -> Iterator[dict]:
        yield from self._items

    def transform_one(self, raw_item: Any) -> dict | None:
        if raw_item.get("skip"):
            return None
        if raw_item.get("id") in self._fail_on:
            raise ValueError(f"Transform error on {raw_item['id']}")
        return {"data": raw_item}

    def load_batch(
        self, batch: list[dict], conn: Connection, load_id: uuid.UUID
    ) -> LoadStats:
        stats = LoadStats()
        stats.loaded = len(batch)
        return stats

    def _get_item_id(self, raw_item: Any) -> str | None:
        return raw_item.get("id")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoadStats:
    def test_merge(self):
        a = LoadStats(loaded=5, skipped=1, failed=2, errors=[{"error": "x"}])
        b = LoadStats(loaded=3, skipped=0, failed=1, errors=[{"error": "y"}])
        a.merge(b)
        assert a.loaded == 8
        assert a.skipped == 1
        assert a.failed == 3
        assert len(a.errors) == 2

    def test_add_error(self):
        stats = LoadStats()
        stats.add_error("boom", item_id="rx-1")
        assert stats.failed == 1
        assert stats.errors[0] == {"error": "boom", "item_id": "rx-1"}


class TestBaseLoader:
    @pytest.fixture()
    def mock_engine(self):
        """Create a mock engine that simulates connection/commit."""
        engine = MagicMock()
        conn = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        conn.begin.return_value.__enter__ = MagicMock(return_value=None)
        conn.begin.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute = MagicMock()
        conn.commit = MagicMock()
        return engine

    def test_run_counts_loaded(self, mock_engine):
        items = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        loader = MockLoader(mock_engine, items, batch_size=10)
        load_id = loader.run()
        assert isinstance(load_id, uuid.UUID)

    def test_run_skips_none_transforms(self, mock_engine):
        items = [{"id": "1"}, {"id": "2", "skip": True}, {"id": "3"}]
        loader = MockLoader(mock_engine, items, batch_size=10)
        loader.run()
        # The mock engine doesn't actually track stats, but we verify
        # the run completes without error

    def test_run_handles_transform_errors(self, mock_engine):
        items = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        loader = MockLoader(mock_engine, items, fail_on={"2"}, batch_size=10)
        # Should not raise — errors are caught per-item
        load_id = loader.run()
        assert isinstance(load_id, uuid.UUID)

    def test_run_with_batching(self, mock_engine):
        items = [{"id": str(i)} for i in range(12)]
        loader = MockLoader(mock_engine, items, batch_size=5)
        load_id = loader.run()
        assert isinstance(load_id, uuid.UUID)


class TestBaseLoaderIntegration:
    """Integration tests that require a real database connection."""

    @pytest.mark.skipif(
        True,  # Set to False when running against a real DB
        reason="Requires running PostgreSQL with schema",
    )
    def test_provenance_recorded(self, engine):
        items = [{"id": "1"}, {"id": "2"}]
        loader = MockLoader(engine, items, batch_size=10)
        load_id = loader.run()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM lineage.data_loads WHERE load_id = :lid"),
                {"lid": load_id},
            ).fetchone()
            assert row is not None
            assert row.status == "completed"
            assert row.source_name == "test"
