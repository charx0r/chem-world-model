"""Abstract base loader with provenance tracking and batch orchestration."""

from __future__ import annotations

import abc
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator

import structlog
from sqlalchemy import Connection, Engine, text, insert, update

from chemworldmodel.db.schema import data_loads

log = structlog.get_logger()

MAX_ERROR_LOG_ENTRIES = 1000


@dataclass
class LoadStats:
    """Tracks counts for a single load run."""

    loaded: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[dict] = field(default_factory=list)

    def merge(self, other: LoadStats) -> None:
        self.loaded += other.loaded
        self.skipped += other.skipped
        self.failed += other.failed
        self.errors.extend(other.errors)

    def add_error(self, error: str, item_id: str | None = None) -> None:
        if len(self.errors) < MAX_ERROR_LOG_ENTRIES:
            entry: dict[str, str] = {"error": error}
            if item_id:
                entry["item_id"] = item_id
            self.errors.append(entry)
        self.failed += 1


class BaseLoader(abc.ABC):
    """Abstract ETL loader with provenance tracking.

    Subclasses implement extract, transform_one, and load_batch.
    The concrete run() method orchestrates the pipeline, tracks provenance
    in lineage.data_loads, and handles batching and error recovery.
    """

    source_name: str
    loader_version: str = "0.1.0"

    def __init__(self, engine: Engine, batch_size: int = 5000):
        self.engine = engine
        self.batch_size = batch_size
        self.log = log.bind(loader=self.source_name)

    @abc.abstractmethod
    def extract(self, **kwargs: Any) -> Iterator[Any]:
        """Yield individual raw items from the data source."""

    @abc.abstractmethod
    def transform_one(self, raw_item: Any) -> dict | None:
        """Transform a single raw item into a structured dict for loading.

        Return None to skip the item.
        """

    @abc.abstractmethod
    def load_batch(
        self, batch: list[dict], conn: Connection, load_id: uuid.UUID
    ) -> LoadStats:
        """Bulk insert a batch of transformed records."""

    def run(self, **kwargs: Any) -> uuid.UUID:
        """Orchestrate the full ETL pipeline with provenance tracking."""
        load_id = self._start_load(kwargs)
        stats = LoadStats()
        batch: list[dict] = []

        try:
            for raw_item in self.extract(**kwargs):
                try:
                    record = self.transform_one(raw_item)
                    if record is None:
                        stats.skipped += 1
                        continue
                    batch.append(record)
                    if len(batch) >= self.batch_size:
                        batch_stats = self._flush_batch(batch, load_id)
                        stats.merge(batch_stats)
                        batch = []
                        self._update_load_progress(load_id, stats)
                except Exception as e:
                    item_id = self._get_item_id(raw_item)
                    stats.add_error(str(e), item_id)
                    self.log.warning(
                        "transform_error", item_id=item_id, error=str(e)
                    )

            # Flush remaining
            if batch:
                batch_stats = self._flush_batch(batch, load_id)
                stats.merge(batch_stats)

            self._finish_load(load_id, "completed", stats)
            self.log.info(
                "load_complete",
                load_id=str(load_id),
                loaded=stats.loaded,
                skipped=stats.skipped,
                failed=stats.failed,
            )

        except Exception as e:
            self.log.error("load_failed", load_id=str(load_id), error=str(e))
            stats.add_error(f"Fatal: {e}")
            self._finish_load(load_id, "failed", stats)
            raise

        return load_id

    def _get_item_id(self, raw_item: Any) -> str | None:
        """Override to extract a human-readable ID from a raw item for error logging."""
        return None

    def _start_load(self, config: dict) -> uuid.UUID:
        load_id = uuid.uuid4()
        with self.engine.connect() as conn:
            conn.execute(
                insert(data_loads).values(
                    load_id=load_id,
                    source_name=self.source_name,
                    loader_version=self.loader_version,
                    config={k: str(v) for k, v in config.items() if v is not None},
                )
            )
            conn.commit()
        self.log.info("load_started", load_id=str(load_id))
        return load_id

    def _flush_batch(self, batch: list[dict], load_id: uuid.UUID) -> LoadStats:
        with self.engine.connect() as conn:
            with conn.begin():
                batch_stats = self.load_batch(batch, conn, load_id)
        self.log.info(
            "batch_flushed",
            batch_size=len(batch),
            loaded=batch_stats.loaded,
        )
        return batch_stats

    def _update_load_progress(self, load_id: uuid.UUID, stats: LoadStats) -> None:
        with self.engine.connect() as conn:
            conn.execute(
                update(data_loads)
                .where(data_loads.c.load_id == load_id)
                .values(
                    records_loaded=stats.loaded,
                    records_skipped=stats.skipped,
                    records_failed=stats.failed,
                )
            )
            conn.commit()

    def _finish_load(
        self, load_id: uuid.UUID, status: str, stats: LoadStats
    ) -> None:
        with self.engine.connect() as conn:
            conn.execute(
                update(data_loads)
                .where(data_loads.c.load_id == load_id)
                .values(
                    status=status,
                    completed_at=text("NOW()"),
                    records_loaded=stats.loaded,
                    records_skipped=stats.skipped,
                    records_failed=stats.failed,
                    error_log=stats.errors[:MAX_ERROR_LOG_ENTRIES] if stats.errors else None,
                )
            )
            conn.commit()
