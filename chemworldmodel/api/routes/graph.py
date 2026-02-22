"""API endpoints for the Apache AGE graph layer."""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, HTTPException, Query

from chemworldmodel.models.graph import GraphStats, RouteSearchResult

router = APIRouter(prefix="/api/graph", tags=["graph"])

# InChIKey format: 14 chars - 10 chars - 1 char (e.g. BSYNRYMUTXBXSQ-UHFFFAOYSA-N)
_INCHIKEY_RE = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")


@router.get("/routes/{inchikey}", response_model=RouteSearchResult)
async def get_routes(
    inchikey: str,
    max_depth: int = Query(default=8, ge=2, le=16),
    max_routes: int = Query(default=10, ge=1, le=50),
) -> RouteSearchResult:
    """Find retrosynthetic routes to a target molecule."""
    if not _INCHIKEY_RE.match(inchikey):
        raise HTTPException(status_code=400, detail="Invalid InChIKey format")

    from chemworldmodel.db.engine import get_sync_engine
    from chemworldmodel.graph.routes import find_routes

    engine = get_sync_engine()

    try:
        return await asyncio.to_thread(
            find_routes, inchikey, engine, max_depth, max_routes
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Graph query error: {e}")


@router.get("/stats", response_model=GraphStats)
async def get_graph_stats() -> GraphStats:
    """Return node and edge counts for the chemworld graph."""
    from chemworldmodel.db.engine import get_sync_engine
    from chemworldmodel.graph.routes import get_graph_stats

    engine = get_sync_engine()

    try:
        return await asyncio.to_thread(get_graph_stats, engine)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Graph stats error: {e}")
