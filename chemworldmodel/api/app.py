from fastapi import FastAPI, HTTPException

from chemworldmodel.models.query import QueryRequest, QueryResult

app = FastAPI(title="ChemWorldModel", version="0.1.0")


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
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Query timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Query pipeline error: {e}")
