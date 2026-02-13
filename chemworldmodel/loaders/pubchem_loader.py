"""PubChem compound enrichment loader (WP5.1).

Enriches chem.molecules with PubChem CID, IUPAC name, exact mass,
XLogP, and complexity via the PUG REST API. Queries by InChIKey in
batches, respecting PubChem's 5 requests/second rate limit.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Iterator

import httpx
import structlog
from sqlalchemy import Connection, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from chemworldmodel.db.schema import molecule_provenance
from chemworldmodel.loaders.base import BaseLoader, LoadStats

log = structlog.get_logger()

# PubChem PUG REST base URL
PUG_REST = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

# Request InChIKey back alongside the enrichment properties so we can
# map results without a second API round-trip.
PROPERTIES = "InChIKey,IUPACName,MolecularWeight,ExactMass,XLogP,Complexity"

# Max InChIKeys per PUG REST request (PubChem limit is ~100 for POST)
PUBCHEM_BATCH_SIZE = 100

# Rate limit: 5 requests/second → 200ms between requests
RATE_LIMIT_DELAY = 0.21


class PubChemLoader(BaseLoader):
    """Enrich molecules with PubChem properties and identifiers.

    Overrides run() because the base extract→transform→load pipeline
    assumes extract yields individual items, but PubChem's API is
    batch-oriented (POST up to 100 InChIKeys at once). The override
    reuses _start_load/_flush_batch/_finish_load from BaseLoader so
    provenance tracking is preserved.
    """

    source_name = "pubchem"

    def extract(self, **kwargs: Any) -> Iterator[Any]:
        """Not used directly — see run()."""
        raise NotImplementedError("PubChemLoader uses a custom run() method")

    def transform_one(self, raw_item: Any) -> dict | None:
        """Not used directly — see run()."""
        raise NotImplementedError("PubChemLoader uses a custom run() method")

    def load_batch(
        self, batch: list[dict], conn: Connection, load_id: uuid.UUID
    ) -> LoadStats:
        """Update molecules with PubChem data and record provenance."""
        stats = LoadStats()

        for record in batch:
            try:
                conn.execute(
                    text(
                        "UPDATE chem.molecules SET "
                        "pubchem_cid = :cid, "
                        "iupac_name = COALESCE(:iupac_name, iupac_name), "
                        "exact_mass = COALESCE(:exact_mass, exact_mass), "
                        "logp = COALESCE(:xlogp, logp), "
                        "complexity = COALESCE(:complexity, complexity), "
                        "updated_at = NOW() "
                        "WHERE inchikey = :inchikey"
                    ),
                    record,
                )
                conn.execute(
                    pg_insert(molecule_provenance)
                    .values(
                        inchikey=record["inchikey"],
                        source_name="pubchem",
                        source_id=str(record["cid"]),
                        load_id=load_id,
                    )
                    .on_conflict_do_update(
                        index_elements=["inchikey", "source_name"],
                        set_={"source_id": str(record["cid"]), "load_id": load_id},
                    )
                )
                stats.loaded += 1
            except Exception as e:
                stats.add_error(str(e), record.get("inchikey"))

        return stats

    def run(self, **kwargs: Any) -> uuid.UUID:
        """Orchestrate PubChem enrichment with batch API calls.

        Overrides BaseLoader.run() because PubChem's PUG REST API is
        batch-oriented (POST up to 100 InChIKeys). We still use the
        base class helpers for provenance tracking and batch flushing.
        """
        load_id = self._start_load(kwargs)
        stats = LoadStats()
        accumulated: list[dict] = []

        limit: int | None = kwargs.get("limit")
        api_batch_size: int = kwargs.get("api_batch_size", PUBCHEM_BATCH_SIZE)

        try:
            with httpx.Client(timeout=30.0) as client:
                for inchikey_batch in self._iter_inchikey_batches(limit, api_batch_size):
                    records = self._fetch_batch(client, inchikey_batch)
                    accumulated.extend(records)
                    stats.skipped += len(inchikey_batch) - len(records)

                    if len(accumulated) >= self.batch_size:
                        batch_stats = self._flush_batch(accumulated, load_id)
                        stats.merge(batch_stats)
                        accumulated = []
                        self._update_load_progress(load_id, stats)

            if accumulated:
                batch_stats = self._flush_batch(accumulated, load_id)
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

    def _iter_inchikey_batches(
        self, limit: int | None, api_batch_size: int
    ) -> Iterator[list[str]]:
        """Yield batches of InChIKeys from chem.molecules that lack a pubchem_cid."""
        with self.engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT inchikey FROM chem.molecules "
                    "WHERE pubchem_cid IS NULL "
                    "ORDER BY inchikey"
                )
            )
            batch: list[str] = []
            count = 0

            for (inchikey,) in result:
                batch.append(inchikey)
                count += 1
                if limit and count >= limit:
                    if batch:
                        yield batch
                    return
                if len(batch) >= api_batch_size:
                    yield batch
                    batch = []

            if batch:
                yield batch

    def _fetch_batch(
        self, client: httpx.Client, inchikeys: list[str]
    ) -> list[dict]:
        """Fetch properties from PubChem for a batch of InChIKeys.

        Returns enrichment dicts ready for load_batch. Uses a single API
        call per batch — InChIKey is included in PROPERTIES so no second
        round-trip is needed.
        """
        url = f"{PUG_REST}/compound/inchikey/property/{PROPERTIES}/JSON"

        try:
            time.sleep(RATE_LIMIT_DELAY)
            resp = client.post(
                url,
                data={"inchikey": ",".join(inchikeys)},
            )

            if resp.status_code == 404:
                self.log.debug("pubchem_batch_not_found", count=len(inchikeys))
                return []

            resp.raise_for_status()
            data = resp.json()

        except httpx.HTTPStatusError as e:
            self.log.warning(
                "pubchem_api_error",
                status=e.response.status_code,
                count=len(inchikeys),
            )
            return []
        except Exception as e:
            self.log.warning("pubchem_request_error", error=str(e))
            return []

        properties = data.get("PropertyTable", {}).get("Properties", [])
        if not properties:
            return []

        # Build results — InChIKey is returned in the response directly
        results: list[dict] = []
        for prop in properties:
            ik = prop.get("InChIKey")
            cid = prop.get("CID")
            if not ik or not cid:
                continue

            results.append({
                "inchikey": ik,
                "cid": cid,
                "iupac_name": prop.get("IUPACName"),
                "exact_mass": prop.get("ExactMass"),
                "xlogp": prop.get("XLogP"),
                "complexity": prop.get("Complexity"),
            })

        return results
