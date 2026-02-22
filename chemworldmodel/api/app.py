import os

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from chemworldmodel.api.routes.graph import router as graph_router
from chemworldmodel.api.routes.molecules import router as molecules_router
from chemworldmodel.api.routes.reactions import router as reactions_router
from chemworldmodel.models.query import QueryRequest, QueryResult

log = structlog.get_logger()

app = FastAPI(title="ChemWorldModel", version="0.1.0")

# CORS — allow the Next.js frontend to connect
_cors_origins = os.environ.get(
    "CORS_ORIGINS", "http://localhost:3000,http://web:3000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(graph_router)
app.include_router(molecules_router)
app.include_router(reactions_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/query", response_model=QueryResult)
async def query_endpoint(request: QueryRequest) -> QueryResult:
    """Execute a natural language chemistry query."""
    from chemworldmodel.config import get_settings
    from chemworldmodel.db.engine import get_sync_engine
    from chemworldmodel.query.nl_to_sql import NLToSQL, SQLValidationError

    settings = get_settings()
    engine = get_sync_engine()
    pipeline = NLToSQL(engine=engine, settings=settings)

    try:
        return await pipeline.query(request.question)
    except SQLValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        from sqlalchemy.exc import OperationalError

        # DB statement_timeout surfaces as OperationalError
        if isinstance(e, OperationalError) and "statement_timeout" in str(e):
            raise HTTPException(status_code=504, detail="Query timed out")
        log.error("query_pipeline_error", error=str(e))
        raise HTTPException(status_code=502, detail="Internal query pipeline error")
