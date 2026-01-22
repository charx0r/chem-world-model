"""Answer grounding — attach reaction ID citations and statistics to LLM answers."""

from __future__ import annotations

from typing import Any

from chemworldmodel.models.query import QueryResult

_NO_DATA_MSG = "I couldn't find data matching your question in the database."

_NUMERIC_STAT_KEYS = ("yield_pct", "temperature_c", "tanimoto", "avg_yield", "reaction_count")

_MAX_CITATIONS = 50
_MAX_RAW_ROWS = 100


def _extract_reaction_ids(results: list[dict[str, Any]]) -> list[str]:
    """Extract and deduplicate reaction_id values from result rows."""
    ids: list[str] = []
    seen: set[str] = set()

    for row in results:
        for key, val in row.items():
            if val is None:
                continue
            # Direct reaction_id column
            if key == "reaction_id" or key.endswith("_reaction_id"):
                rid = str(val)
                if rid not in seen:
                    ids.append(rid)
                    seen.add(rid)
            # Array of reaction_ids (from ARRAY_AGG)
            elif "reaction_id" in key and isinstance(val, (list, tuple)):
                for item in val:
                    if item is not None:
                        rid = str(item)
                        if rid not in seen:
                            ids.append(rid)
                            seen.add(rid)

    return ids


def _compute_statistics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate statistics from result rows."""
    stats: dict[str, Any] = {"row_count": len(results)}

    for key in _NUMERIC_STAT_KEYS:
        values = [
            row[key]
            for row in results
            if key in row and row[key] is not None and isinstance(row[key], (int, float))
        ]
        if values:
            stats[key] = {
                "count": len(values),
                "avg": round(sum(values) / len(values), 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
            }

    return stats


def ground_answer(
    raw_results: list[dict[str, Any]],
    llm_summary: str,
    sql: str,
) -> QueryResult:
    """Attach citations, statistics, and data to the LLM-generated summary.

    Args:
        raw_results: Rows returned from the SQL query.
        llm_summary: Natural language answer from the LLM.
        sql: The SQL query that was executed.

    Returns:
        A fully grounded QueryResult.
    """
    if not raw_results:
        return QueryResult(
            answer=_NO_DATA_MSG,
            sql=sql,
            citations=[],
            reaction_count=0,
            statistics={"row_count": 0},
            raw_data=[],
        )

    all_citations = _extract_reaction_ids(raw_results)
    statistics = _compute_statistics(raw_results)

    return QueryResult(
        answer=llm_summary,
        sql=sql,
        citations=all_citations[:_MAX_CITATIONS],
        reaction_count=len(all_citations),
        statistics=statistics,
        raw_data=raw_results[:_MAX_RAW_ROWS],
    )
