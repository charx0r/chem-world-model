"""ChEMBL bioactivity loader (WP5.4).

Reads the ChEMBL SQLite dump, extracts bioactivity data (activities,
targets), links molecules via InChIKey, and populates chem.bioactivities.
Optionally creates :HAS_ACTIVITY edges in the AGE graph.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterator

import structlog
from sqlalchemy import Connection, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from chemworldmodel.db.schema import bioactivities, molecule_provenance, molecules
from chemworldmodel.loaders.base import BaseLoader, LoadStats

log = structlog.get_logger()

# SQL to extract activities with target info and InChIKey from ChEMBL SQLite
CHEMBL_EXTRACT_SQL = """
SELECT
    a.standard_type     AS activity_type,
    a.standard_value    AS value,
    a.standard_units    AS unit,
    a.standard_relation AS relation,
    ass.chembl_id       AS assay_chembl_id,
    cs.standard_inchi_key AS inchikey,
    md.chembl_id        AS molecule_chembl_id,
    td.chembl_id        AS target_chembl_id,
    td.pref_name        AS target_name,
    td.organism         AS target_organism
FROM activities a
JOIN assays ass ON a.assay_id = ass.assay_id
JOIN target_dictionary td ON ass.tid = td.tid
JOIN molecule_dictionary md ON a.molregno = md.molregno
JOIN compound_structures cs ON md.molregno = cs.molregno
WHERE cs.standard_inchi_key IS NOT NULL
  AND a.standard_type IS NOT NULL
  AND a.standard_value IS NOT NULL
  AND td.chembl_id IS NOT NULL
ORDER BY cs.standard_inchi_key
"""

CHEMBL_EXTRACT_SQL_LIMITED = CHEMBL_EXTRACT_SQL.rstrip() + "\nLIMIT ?"


class ChEMBLLoader(BaseLoader):
    """Load bioactivity data from ChEMBL SQLite dump."""

    source_name = "chembl"

    def extract(self, **kwargs: Any) -> Iterator[Any]:
        """Yield activity rows from the ChEMBL SQLite database."""
        db_path: Path = kwargs["db_path"]
        limit: int | None = kwargs.get("limit")

        if not db_path.exists():
            raise FileNotFoundError(f"ChEMBL SQLite database not found: {db_path}")

        self.log.info("opening_chembl_db", path=str(db_path))
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        try:
            if limit:
                cursor = conn.execute(CHEMBL_EXTRACT_SQL_LIMITED, (int(limit),))
            else:
                cursor = conn.execute(CHEMBL_EXTRACT_SQL)

            for row in cursor:
                yield dict(row)
        finally:
            conn.close()

    def transform_one(self, raw_item: Any) -> dict | None:
        """Validate and clean a ChEMBL activity record."""
        row = raw_item

        inchikey = row.get("inchikey")
        if not inchikey or len(inchikey) != 27:
            return None

        activity_type = row.get("activity_type")
        if not activity_type:
            return None

        assay_chembl_id = row.get("assay_chembl_id")
        if not assay_chembl_id:
            return None

        value = row.get("value")
        try:
            value = float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

        return {
            "inchikey": inchikey,
            "target_chembl_id": row["target_chembl_id"],
            "target_name": row.get("target_name"),
            "target_organism": row.get("target_organism"),
            "activity_type": activity_type,
            "value": value,
            "unit": row.get("unit"),
            "relation": row.get("relation"),
            "assay_chembl_id": assay_chembl_id,
            "source_chembl_id": row.get("molecule_chembl_id"),
        }

    def load_batch(
        self, batch: list[dict], conn: Connection, load_id: uuid.UUID
    ) -> LoadStats:
        """Insert bioactivity records and update molecule chembl_id references."""
        stats = LoadStats()

        # Filter to molecules that exist in our database
        inchikeys = list({r["inchikey"] for r in batch})
        existing = set()
        for chunk_start in range(0, len(inchikeys), 500):
            chunk = inchikeys[chunk_start : chunk_start + 500]
            result = conn.execute(
                text(
                    "SELECT inchikey FROM chem.molecules "
                    "WHERE inchikey = ANY(:keys)"
                ),
                {"keys": chunk},
            )
            existing.update(row[0] for row in result)

        # Filter batch to existing molecules
        valid_records = [r for r in batch if r["inchikey"] in existing]
        stats.skipped += len(batch) - len(valid_records)

        if not valid_records:
            return stats

        # Bulk upsert bioactivities
        for record in valid_records:
            try:
                conn.execute(
                    pg_insert(bioactivities)
                    .values(
                        inchikey=record["inchikey"],
                        target_chembl_id=record["target_chembl_id"],
                        target_name=record.get("target_name"),
                        target_organism=record.get("target_organism"),
                        activity_type=record["activity_type"],
                        value=record.get("value"),
                        unit=record.get("unit"),
                        relation=record.get("relation"),
                        assay_chembl_id=record.get("assay_chembl_id"),
                        source_chembl_id=record.get("source_chembl_id"),
                    )
                    .on_conflict_do_update(
                        constraint="uq_bioact_mol_target_type_assay",
                        set_={
                            "value": record.get("value"),
                            "unit": record.get("unit"),
                            "relation": record.get("relation"),
                            "target_name": record.get("target_name"),
                            "target_organism": record.get("target_organism"),
                        },
                    )
                )
                stats.loaded += 1
            except Exception as e:
                stats.add_error(str(e), record["inchikey"])

        # Update chembl_id on molecules and record provenance
        chembl_map: dict[str, str] = {}
        for record in valid_records:
            ik = record["inchikey"]
            cid = record.get("source_chembl_id")
            if cid and ik not in chembl_map:
                chembl_map[ik] = cid

        for inchikey, chembl_id in chembl_map.items():
            try:
                conn.execute(
                    text(
                        "UPDATE chem.molecules SET chembl_id = :chembl_id, "
                        "updated_at = NOW() "
                        "WHERE inchikey = :inchikey AND chembl_id IS NULL"
                    ),
                    {"inchikey": inchikey, "chembl_id": chembl_id},
                )
                conn.execute(
                    pg_insert(molecule_provenance)
                    .values(
                        inchikey=inchikey,
                        source_name="chembl",
                        source_id=chembl_id,
                        load_id=load_id,
                    )
                    .on_conflict_do_update(
                        index_elements=["inchikey", "source_name"],
                        set_={"source_id": chembl_id, "load_id": load_id},
                    )
                )
            except Exception as e:
                self.log.debug(
                    "chembl_provenance_error", inchikey=inchikey, error=str(e)
                )

        return stats
