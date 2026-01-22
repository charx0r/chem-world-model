"""Molecular similarity search via pgvector Tanimoto distance."""

from __future__ import annotations

from sqlalchemy import Engine, text

from chemworldmodel.models.query import SimilarMolecule

SIMILARITY_SQL = text("""\
SELECT m.inchikey, m.canonical_smiles,
       1 - (m.fp_morgan <%> morganbv_fp(
           mol_from_smiles(:smiles\\::cstring), 2, 2048
       )) AS tanimoto
FROM chem.molecules m
WHERE m.fp_morgan IS NOT NULL
  AND m.fp_morgan <%> morganbv_fp(
      mol_from_smiles(:smiles\\::cstring), 2, 2048
  ) < :distance_threshold
ORDER BY m.fp_morgan <%> morganbv_fp(
    mol_from_smiles(:smiles\\::cstring), 2, 2048
)
LIMIT :limit
""")


def find_similar_molecules(
    smiles: str,
    engine: Engine,
    threshold: float = 0.7,
    limit: int = 50,
) -> list[SimilarMolecule]:
    """Find molecules with Tanimoto similarity above threshold.

    Args:
        smiles: Query SMILES string.
        engine: SQLAlchemy sync engine.
        threshold: Minimum Tanimoto similarity (0-1). Default 0.7.
        limit: Maximum results to return.

    Returns:
        List of SimilarMolecule sorted by descending similarity.
    """
    distance_threshold = 1.0 - threshold

    with engine.connect() as conn:
        rows = conn.execute(
            SIMILARITY_SQL,
            {"smiles": smiles, "distance_threshold": distance_threshold, "limit": limit},
        ).fetchall()

    return [
        SimilarMolecule(
            inchikey=row.inchikey,
            canonical_smiles=row.canonical_smiles,
            tanimoto=round(row.tanimoto, 4),
        )
        for row in rows
    ]
