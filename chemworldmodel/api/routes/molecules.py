"""API endpoints for molecule lookup and search."""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Engine, text

from chemworldmodel.models.molecules import (
    BioactivityInfo,
    HazardInfo,
    MoleculeDetail,
    MoleculeSearchResult,
    ReactionSummary,
    SimilarMoleculeHit,
)

log = structlog.get_logger()

router = APIRouter(prefix="/api/molecules", tags=["molecules"])


# ---------------------------------------------------------------------------
# SQL queries
# ---------------------------------------------------------------------------

_MOLECULE_SQL = text("""
    SELECT m.inchikey, m.canonical_smiles, m.iupac_name, m.mol_formula,
           m.mol_weight, m.exact_mass, m.logp, m.tpsa, m.hba, m.hbd,
           m.num_rotatable, m.num_rings, m.complexity, m.pubchem_cid,
           m.chembl_id, m.chebi_id, m.cas_number, m.commercially_available,
           m.sources
    FROM chem.molecules m
    WHERE m.inchikey = :inchikey
""")

_HAZARD_SQL = text("""
    SELECT h.ghs_codes, h.signal_word, h.pictograms, h.source
    FROM onto.hazard_data h
    WHERE h.inchikey = :inchikey
""")

_BIOACTIVITY_SQL = text("""
    SELECT b.target_name, b.target_organism, b.activity_type, b.value, b.unit
    FROM chem.bioactivities b
    WHERE b.inchikey = :inchikey
    LIMIT 50
""")

_REACTIONS_SQL = text("""
    SELECT rc.reaction_id, r.reaction_class, rc.role, rc.yield_pct
    FROM rxn.reaction_components rc
    JOIN rxn.reactions r ON r.reaction_id = rc.reaction_id
    WHERE rc.inchikey = :inchikey
    LIMIT 100
""")

_SUBSTRUCTURE_SQL = text("""
    SELECT m.inchikey, m.canonical_smiles, m.iupac_name, m.mol_formula,
           m.mol_weight, m.exact_mass, m.logp, m.tpsa, m.hba, m.hbd,
           m.num_rotatable, m.num_rings, m.complexity, m.pubchem_cid,
           m.chembl_id, m.chebi_id, m.cas_number, m.commercially_available,
           m.sources
    FROM chem.molecules m
    WHERE m.mol @> mol_from_smarts(:pattern)
    ORDER BY m.mol_weight
    LIMIT :limit OFFSET :offset
""")

_SUBSTRUCTURE_COUNT_SQL = text("""
    SELECT COUNT(*) FROM chem.molecules m
    WHERE m.mol @> mol_from_smarts(:pattern)
""")


# ---------------------------------------------------------------------------
# Blocking helpers (called via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _get_molecule_detail(inchikey: str, engine: Engine) -> MoleculeDetail:
    """Fetch full molecule detail from the database."""
    with engine.connect() as conn:
        row = conn.execute(_MOLECULE_SQL, {"inchikey": inchikey}).mappings().fetchone()
        if row is None:
            raise KeyError(inchikey)

        smiles = row["canonical_smiles"]

        hazards = [
            HazardInfo(**dict(r))
            for r in conn.execute(_HAZARD_SQL, {"inchikey": inchikey}).mappings()
        ]

        reactions = [
            ReactionSummary(**dict(r))
            for r in conn.execute(_REACTIONS_SQL, {"inchikey": inchikey}).mappings()
        ]

        bioactivities = [
            BioactivityInfo(**dict(r))
            for r in conn.execute(_BIOACTIVITY_SQL, {"inchikey": inchikey}).mappings()
        ]

    # Similarity search uses its own connection
    similar: list[SimilarMoleculeHit] = []
    if smiles:
        try:
            from chemworldmodel.query.similarity import find_similar_molecules

            hits = find_similar_molecules(smiles, engine, threshold=0.7, limit=10)
            similar = [
                SimilarMoleculeHit(
                    inchikey=h.inchikey,
                    canonical_smiles=h.canonical_smiles,
                    tanimoto=h.tanimoto,
                )
                for h in hits
                if h.inchikey != inchikey  # exclude self
            ]
        except Exception:
            pass  # similarity is best-effort

    return MoleculeDetail(
        **{k: v for k, v in dict(row).items() if k != "sources"},
        sources=list(row["sources"] or []),
        hazards=hazards,
        bioactivities=bioactivities,
        reactions=reactions,
        similar=similar,
    )


def _search_substructure(
    pattern: str, engine: Engine, limit: int, offset: int
) -> MoleculeSearchResult:
    """Run substructure search via RDKit cartridge."""
    with engine.connect() as conn:
        total = conn.execute(
            _SUBSTRUCTURE_COUNT_SQL, {"pattern": pattern}
        ).scalar() or 0

        rows = conn.execute(
            _SUBSTRUCTURE_SQL,
            {"pattern": pattern, "limit": limit, "offset": offset},
        ).mappings().fetchall()

    molecules = [
        MoleculeDetail(
            **{k: v for k, v in dict(r).items() if k != "sources"},
            sources=list(r["sources"] or []),
        )
        for r in rows
    ]

    return MoleculeSearchResult(
        molecules=molecules, total=total, offset=offset, limit=limit
    )


def _search_similarity(
    pattern: str, engine: Engine, threshold: float, limit: int
) -> MoleculeSearchResult:
    """Run similarity search via find_similar_molecules."""
    from chemworldmodel.query.similarity import find_similar_molecules

    hits = find_similar_molecules(pattern, engine, threshold=threshold, limit=limit)
    molecules = [
        MoleculeDetail(inchikey=h.inchikey, canonical_smiles=h.canonical_smiles)
        for h in hits
    ]
    return MoleculeSearchResult(
        molecules=molecules, total=len(molecules), offset=0, limit=limit
    )


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


_BROWSE_COLS = """m.inchikey, m.canonical_smiles, m.iupac_name, m.mol_formula,
           m.mol_weight, m.exact_mass, m.logp, m.tpsa, m.hba, m.hbd,
           m.num_rotatable, m.num_rings, m.complexity, m.pubchem_cid,
           m.chembl_id, m.chebi_id, m.cas_number, m.commercially_available,
           m.sources"""

_BROWSE_ALL_SQL = text(f"""
    SELECT {_BROWSE_COLS} FROM chem.molecules m
    ORDER BY m.mol_weight ASC NULLS LAST
    LIMIT :limit OFFSET :offset
""")

_BROWSE_FILTER_SQL = text(f"""
    SELECT {_BROWSE_COLS} FROM chem.molecules m
    WHERE m.iupac_name ILIKE '%' || :q || '%'
    ORDER BY m.mol_weight ASC NULLS LAST
    LIMIT :limit OFFSET :offset
""")

_BROWSE_COUNT_ALL_SQL = text("SELECT COUNT(*) FROM chem.molecules")

_BROWSE_COUNT_FILTER_SQL = text("""
    SELECT COUNT(*) FROM chem.molecules m
    WHERE m.iupac_name ILIKE '%' || :q || '%'
""")


def _browse_molecules(
    engine: Engine, q: str | None, limit: int, offset: int
) -> MoleculeSearchResult:
    """Browse molecules with optional name search."""
    with engine.connect() as conn:
        if q:
            total = conn.execute(_BROWSE_COUNT_FILTER_SQL, {"q": q}).scalar() or 0
            rows = conn.execute(
                _BROWSE_FILTER_SQL, {"q": q, "limit": limit, "offset": offset}
            ).mappings().fetchall()
        else:
            total = conn.execute(_BROWSE_COUNT_ALL_SQL).scalar() or 0
            rows = conn.execute(
                _BROWSE_ALL_SQL, {"limit": limit, "offset": offset}
            ).mappings().fetchall()

    molecules = [
        MoleculeDetail(
            **{k: v for k, v in dict(r).items() if k != "sources"},
            sources=list(r["sources"] or []),
        )
        for r in rows
    ]
    return MoleculeSearchResult(
        molecules=molecules, total=total, offset=offset, limit=limit
    )


@router.get("/browse", response_model=MoleculeSearchResult)
async def browse_molecules(
    q: str | None = Query(default=None, max_length=500, description="Name search (ILIKE)"),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> MoleculeSearchResult:
    """Browse molecules with optional name filtering."""
    from chemworldmodel.db.engine import get_sync_engine

    engine = get_sync_engine()

    try:
        return await asyncio.to_thread(_browse_molecules, engine, q, limit, offset)
    except Exception as e:
        log.error("browse_molecules_error", error=str(e))
        raise HTTPException(status_code=502, detail="Browse failed")


@router.get("/search", response_model=MoleculeSearchResult)
async def search_molecules(
    pattern: str = Query(..., min_length=1, max_length=2000, description="SMILES or SMARTS pattern"),
    mode: str = Query(default="substructure", pattern="^(substructure|similarity)$"),
    threshold: float = Query(default=0.7, ge=0.0, le=1.0),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> MoleculeSearchResult:
    """Search molecules by substructure or similarity."""
    from chemworldmodel.db.engine import get_sync_engine

    engine = get_sync_engine()

    if mode == "substructure":
        # Validate SMARTS
        from rdkit import Chem

        mol = Chem.MolFromSmarts(pattern)
        if mol is None:
            raise HTTPException(status_code=400, detail="Invalid SMARTS pattern")

        try:
            return await asyncio.to_thread(
                _search_substructure, pattern, engine, limit, offset
            )
        except Exception as e:
            log.error("substructure_search_error", error=str(e))
            raise HTTPException(status_code=502, detail="Search failed")

    else:  # similarity
        from rdkit import Chem

        mol = Chem.MolFromSmiles(pattern)
        if mol is None:
            raise HTTPException(status_code=400, detail="Invalid SMILES for similarity search")

        try:
            return await asyncio.to_thread(
                _search_similarity, pattern, engine, threshold, limit
            )
        except Exception as e:
            log.error("similarity_search_error", error=str(e))
            raise HTTPException(status_code=502, detail="Search failed")


@router.get("/{inchikey}", response_model=MoleculeDetail)
async def get_molecule(inchikey: str) -> MoleculeDetail:
    """Get full detail for a molecule by InChIKey."""
    from chemworldmodel.db.engine import get_sync_engine
    from chemworldmodel.graph import INCHIKEY_RE

    if not INCHIKEY_RE.match(inchikey):
        raise HTTPException(status_code=400, detail="Invalid InChIKey format")

    engine = get_sync_engine()

    try:
        return await asyncio.to_thread(_get_molecule_detail, inchikey, engine)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Molecule {inchikey} not found"
        )
    except Exception as e:
        log.error("molecule_detail_error", inchikey=inchikey, error=str(e))
        raise HTTPException(status_code=502, detail="Database error")
