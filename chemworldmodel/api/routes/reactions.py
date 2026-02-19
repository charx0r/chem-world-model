"""API endpoints for reaction lookup and search."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Engine, text

from chemworldmodel.models.reactions import (
    ReactionComponent,
    ReactionCondition,
    ReactionDetail,
    ReactionSearchResult,
)

log = structlog.get_logger()

router = APIRouter(prefix="/api/reactions", tags=["reactions"])


# ---------------------------------------------------------------------------
# SQL queries
# ---------------------------------------------------------------------------

_REACTION_SQL = text("""
    SELECT r.reaction_id, r.reaction_smiles, r.reaction_class,
           r.temperature_c, r.pressure_bar, r.time_seconds, r.atmosphere,
           r.yield_pct, r.yield_type, r.selectivity, r.source, r.source_id,
           r.doi, r.patent_id
    FROM rxn.reactions r
    WHERE r.reaction_id = :reaction_id
""")

_COMPONENTS_SQL = text("""
    SELECT rc.inchikey, m.canonical_smiles, rc.role, rc.equivalents,
           rc.mass_g, rc.volume_ml, rc.yield_pct
    FROM rxn.reaction_components rc
    LEFT JOIN chem.molecules m ON m.inchikey = rc.inchikey
    WHERE rc.reaction_id = :reaction_id
""")

_CONDITIONS_SQL = text("""
    SELECT c.condition_type, c.value, c.unit, c.phase
    FROM rxn.reaction_conditions c
    WHERE c.reaction_id = :reaction_id
""")


# ---------------------------------------------------------------------------
# Blocking helpers
# ---------------------------------------------------------------------------


def _get_reaction_detail(reaction_id: str, engine: Engine) -> ReactionDetail:
    """Fetch full reaction detail from the database."""
    with engine.connect() as conn:
        row = conn.execute(
            _REACTION_SQL, {"reaction_id": reaction_id}
        ).mappings().fetchone()
        if row is None:
            raise KeyError(reaction_id)

        components = [
            ReactionComponent(**dict(r))
            for r in conn.execute(
                _COMPONENTS_SQL, {"reaction_id": reaction_id}
            ).mappings()
        ]

        conditions = [
            ReactionCondition(**dict(r))
            for r in conn.execute(
                _CONDITIONS_SQL, {"reaction_id": reaction_id}
            ).mappings()
        ]

    return ReactionDetail(
        **dict(row),
        components=components,
        conditions=conditions,
    )


def _search_reactions(
    engine: Engine,
    reaction_class: str | None,
    min_yield: float | None,
    max_yield: float | None,
    min_temp: float | None,
    max_temp: float | None,
    atmosphere: str | None,
    limit: int,
    offset: int,
) -> ReactionSearchResult:
    """Search reactions with dynamic filters."""
    clauses: list[str] = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if reaction_class is not None:
        clauses.append("r.reaction_class = :reaction_class")
        params["reaction_class"] = reaction_class
    if min_yield is not None:
        clauses.append("r.yield_pct >= :min_yield")
        params["min_yield"] = min_yield
    if max_yield is not None:
        clauses.append("r.yield_pct <= :max_yield")
        params["max_yield"] = max_yield
    if min_temp is not None:
        clauses.append("r.temperature_c >= :min_temp")
        params["min_temp"] = min_temp
    if max_temp is not None:
        clauses.append("r.temperature_c <= :max_temp")
        params["max_temp"] = max_temp
    if atmosphere is not None:
        clauses.append("r.atmosphere = :atmosphere")
        params["atmosphere"] = atmosphere

    where = " AND ".join(clauses) if clauses else "TRUE"

    count_sql = text(f"SELECT COUNT(*) FROM rxn.reactions r WHERE {where}")
    search_sql = text(
        f"SELECT r.reaction_id, r.reaction_smiles, r.reaction_class,"
        f"       r.temperature_c, r.pressure_bar, r.time_seconds, r.atmosphere,"
        f"       r.yield_pct, r.yield_type, r.selectivity, r.source, r.source_id,"
        f"       r.doi, r.patent_id"
        f"  FROM rxn.reactions r"
        f" WHERE {where}"
        f" ORDER BY r.yield_pct DESC NULLS LAST"
        f" LIMIT :limit OFFSET :offset"
    )

    with engine.connect() as conn:
        total = conn.execute(count_sql, params).scalar() or 0
        rows = conn.execute(search_sql, params).mappings().fetchall()

    reactions = [ReactionDetail(**dict(r)) for r in rows]
    return ReactionSearchResult(
        reactions=reactions, total=total, offset=offset, limit=limit
    )


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


_BROWSE_COLS_RXN = """r.reaction_id, r.reaction_smiles, r.reaction_class,
           r.temperature_c, r.pressure_bar, r.time_seconds, r.atmosphere,
           r.yield_pct, r.yield_type, r.selectivity, r.source, r.source_id,
           r.doi, r.patent_id"""

_BROWSE_ALL_RXN_SQL = text(f"""
    SELECT {_BROWSE_COLS_RXN} FROM rxn.reactions r
    ORDER BY r.yield_pct DESC NULLS LAST
    LIMIT :limit OFFSET :offset
""")

_BROWSE_FILTER_RXN_SQL = text(f"""
    SELECT {_BROWSE_COLS_RXN} FROM rxn.reactions r
    WHERE r.reaction_smiles ILIKE '%' || :q || '%'
    ORDER BY r.yield_pct DESC NULLS LAST
    LIMIT :limit OFFSET :offset
""")

_BROWSE_COUNT_ALL_RXN_SQL = text("SELECT COUNT(*) FROM rxn.reactions")

_BROWSE_COUNT_FILTER_RXN_SQL = text("""
    SELECT COUNT(*) FROM rxn.reactions r
    WHERE r.reaction_smiles ILIKE '%' || :q || '%'
""")


def _browse_reactions(
    engine: Engine, q: str | None, limit: int, offset: int
) -> ReactionSearchResult:
    """Browse reactions with optional SMILES text search."""
    with engine.connect() as conn:
        if q:
            total = conn.execute(_BROWSE_COUNT_FILTER_RXN_SQL, {"q": q}).scalar() or 0
            rows = conn.execute(
                _BROWSE_FILTER_RXN_SQL, {"q": q, "limit": limit, "offset": offset}
            ).mappings().fetchall()
        else:
            total = conn.execute(_BROWSE_COUNT_ALL_RXN_SQL).scalar() or 0
            rows = conn.execute(
                _BROWSE_ALL_RXN_SQL, {"limit": limit, "offset": offset}
            ).mappings().fetchall()

    reactions = [ReactionDetail(**dict(r)) for r in rows]
    return ReactionSearchResult(
        reactions=reactions, total=total, offset=offset, limit=limit
    )


@router.get("/browse", response_model=ReactionSearchResult)
async def browse_reactions(
    q: str | None = Query(default=None, max_length=500, description="Text search in reaction SMILES"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ReactionSearchResult:
    """Browse reactions with optional text filtering."""
    from chemworldmodel.db.engine import get_sync_engine

    engine = get_sync_engine()

    try:
        return await asyncio.to_thread(_browse_reactions, engine, q, limit, offset)
    except Exception as e:
        log.error("browse_reactions_error", error=str(e))
        raise HTTPException(status_code=502, detail="Browse failed")


@router.get("/search", response_model=ReactionSearchResult)
async def search_reactions(
    reaction_class: str | None = Query(default=None, description="Filter by reaction class"),
    min_yield: float | None = Query(default=None, ge=0, le=100, description="Minimum yield %"),
    max_yield: float | None = Query(default=None, ge=0, le=100, description="Maximum yield %"),
    min_temp: float | None = Query(default=None, description="Minimum temperature (C)"),
    max_temp: float | None = Query(default=None, description="Maximum temperature (C)"),
    atmosphere: str | None = Query(default=None, description="Atmosphere (e.g. nitrogen, argon)"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ReactionSearchResult:
    """Search reactions by class, yield range, temperature, and conditions."""
    from chemworldmodel.db.engine import get_sync_engine

    engine = get_sync_engine()

    try:
        return await asyncio.to_thread(
            _search_reactions,
            engine,
            reaction_class,
            min_yield,
            max_yield,
            min_temp,
            max_temp,
            atmosphere,
            limit,
            offset,
        )
    except Exception as e:
        log.error("reaction_search_error", error=str(e))
        raise HTTPException(status_code=502, detail="Search failed")


@router.get("/{reaction_id}", response_model=ReactionDetail)
async def get_reaction(reaction_id: str) -> ReactionDetail:
    """Get full detail for a reaction by ID."""
    from chemworldmodel.db.engine import get_sync_engine

    engine = get_sync_engine()

    try:
        return await asyncio.to_thread(_get_reaction_detail, reaction_id, engine)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Reaction {reaction_id} not found"
        )
    except Exception as e:
        log.error("reaction_detail_error", reaction_id=reaction_id, error=str(e))
        raise HTTPException(status_code=502, detail="Database error")
