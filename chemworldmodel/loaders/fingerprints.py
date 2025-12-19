"""Post-load fingerprint and mol column computation via PG RDKit cartridge.

Runs batch UPDATEs against molecules missing mol/fp_morgan columns,
delegating the heavy computation to PostgreSQL's RDKit extension.
"""

from __future__ import annotations

import structlog
from sqlalchemy import Engine, text

log = structlog.get_logger()


def compute_mol_column(engine: Engine, batch_size: int = 50000) -> int:
    """Populate the mol column for molecules where it is NULL.

    Uses the RDKit cartridge's mol_from_smiles() function.
    Returns the total number of rows updated.
    """
    total = 0
    with engine.connect() as conn:
        while True:
            result = conn.execute(text("""
                UPDATE chem.molecules
                SET mol = mol_from_smiles(canonical_smiles::cstring)
                WHERE inchikey IN (
                    SELECT inchikey FROM chem.molecules
                    WHERE mol IS NULL AND canonical_smiles IS NOT NULL
                    LIMIT :batch_size
                    FOR UPDATE SKIP LOCKED
                )
            """), {"batch_size": batch_size})
            conn.commit()

            updated = result.rowcount
            if updated == 0:
                break
            total += updated
            log.info("mol_column_batch", updated=updated, total=total)

    log.info("mol_column_complete", total=total)
    return total


def compute_fingerprints(engine: Engine, batch_size: int = 50000) -> int:
    """Compute Morgan/ECFP4 fingerprints for molecules missing them.

    Uses the RDKit cartridge's morganbv_fp() function (radius=2, 2048 bits).
    Populates both fp_morgan (bit(2048)) and fp_morgan_vec (vector(2048)).
    Returns the total number of rows updated.
    """
    total = 0
    with engine.connect() as conn:
        while True:
            result = conn.execute(text("""
                UPDATE chem.molecules
                SET fp_morgan = morganbv_fp(mol, 2, 2048),
                    fp_morgan_vec = morganbv_fp(mol, 2, 2048)::text::vector(2048)
                WHERE inchikey IN (
                    SELECT inchikey FROM chem.molecules
                    WHERE fp_morgan IS NULL AND mol IS NOT NULL
                    LIMIT :batch_size
                    FOR UPDATE SKIP LOCKED
                )
            """), {"batch_size": batch_size})
            conn.commit()

            updated = result.rowcount
            if updated == 0:
                break
            total += updated
            log.info("fingerprint_batch", updated=updated, total=total)

    log.info("fingerprints_complete", total=total)
    return total


def backfill_all(engine: Engine, batch_size: int = 50000) -> None:
    """Run mol column population followed by fingerprint computation."""
    mol_count = compute_mol_column(engine, batch_size)
    fp_count = compute_fingerprints(engine, batch_size)
    log.info("backfill_complete", mol_updated=mol_count, fp_updated=fp_count)
