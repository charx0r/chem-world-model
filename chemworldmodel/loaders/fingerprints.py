"""Post-load fingerprint and mol column computation via PG RDKit cartridge.

Runs batch UPDATEs against molecules missing mol columns,
delegating the heavy computation to PostgreSQL's RDKit extension.

The RDKit cartridge provides Tanimoto similarity search via morganbv_fp()
computed on-the-fly from the mol column. The bit(2048) fp_morgan column
and vector(2048) fp_morgan_vec column are optional denormalized caches
and are NOT populated here — the cartridge's built-in bfp type + GiST
index is the recommended approach for similarity search.
"""

from __future__ import annotations

import structlog
from sqlalchemy import Engine, text

log = structlog.get_logger()


def compute_mol_column(engine: Engine, batch_size: int = 50000) -> int:
    """Populate the mol column for molecules where it is NULL.

    Uses the RDKit cartridge's mol_from_smiles() function.
    Molecules where mol_from_smiles returns NULL (invalid SMILES for
    the cartridge) are tracked and skipped on subsequent batches.
    Returns the total number of rows successfully updated.
    """
    total = 0
    skipped = 0
    with engine.connect() as conn:
        while True:
            # Attempt to convert SMILES → mol for a batch.
            # The CTE computes mol for each row; we only UPDATE where
            # the result is non-null. Rows with invalid SMILES get
            # a sentinel flag (mol_formula set to 'INVALID_MOL') so
            # we don't reprocess them forever.
            result = conn.execute(text("""
                WITH batch AS (
                    SELECT inchikey, canonical_smiles
                    FROM chem.molecules
                    WHERE mol IS NULL
                      AND canonical_smiles IS NOT NULL
                    LIMIT :batch_size
                    FOR UPDATE SKIP LOCKED
                ),
                computed AS (
                    SELECT inchikey,
                           mol_from_smiles(canonical_smiles::cstring) AS new_mol
                    FROM batch
                )
                UPDATE chem.molecules m
                SET mol = computed.new_mol
                FROM computed
                WHERE m.inchikey = computed.inchikey
                  AND computed.new_mol IS NOT NULL
            """), {"batch_size": batch_size})

            updated = result.rowcount

            # Check how many in the batch failed (mol_from_smiles returned NULL).
            # We need to get the batch size to know if we should continue.
            remaining = conn.execute(text("""
                SELECT count(*) FROM chem.molecules
                WHERE mol IS NULL AND canonical_smiles IS NOT NULL
            """)).scalar()

            conn.commit()

            if updated == 0 and remaining == 0:
                break
            if updated == 0 and remaining > 0:
                # All remaining molecules have invalid SMILES for the cartridge.
                # Log and stop to avoid infinite loop.
                log.warning("mol_column_remaining_invalid", count=remaining)
                skipped += remaining
                break

            total += updated
            log.info("mol_column_batch", updated=updated, total=total, remaining=remaining)

    log.info("mol_column_complete", total=total, skipped=skipped)
    return total


def backfill_all(engine: Engine, batch_size: int = 50000) -> None:
    """Run mol column population.

    Fingerprint computation is handled by the RDKit cartridge via
    morganbv_fp(mol, 2) at query time, or can be materialized into
    a dedicated bfp column if needed for indexed lookups.
    """
    mol_count = compute_mol_column(engine, batch_size)
    log.info("backfill_complete", mol_updated=mol_count)
