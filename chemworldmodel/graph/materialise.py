"""Materialise derived edges in the Apache AGE graph.

- **SIMILAR_TO**: Pre-computed molecular similarity edges (Tanimoto ≥ threshold)
  using pgvector KNN from the relational fingerprint columns.
- **PRECURSOR_OF**: Shortcut edges for multi-step synthesis paths (depth 2–5)
  with step_count and cumulative_yield properties.
- **HAS_HAZARD**: Links molecules to their GHS hazard classification
  (signal_word property on the edge).
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from chemworldmodel.graph import (
    _format_agtype_map,
    age_connection,
    age_execute,
)

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# SIMILAR_TO edges
# ---------------------------------------------------------------------------


def materialise_similar_to(
    engine: Engine,
    threshold: float = 0.85,
    batch_size: int = 10000,
) -> int:
    """Create SIMILAR_TO edges for molecule pairs above a Tanimoto threshold.

    Uses pgvector's HNSW index via CROSS JOIN LATERAL to find top-K
    nearest neighbours per molecule, filtered to Tanimoto ≥ threshold.
    Only creates one directed edge per pair (where ik_a < ik_b).

    Parameters
    ----------
    engine:
        SQLAlchemy engine.
    threshold:
        Minimum Tanimoto similarity (default 0.85).
    batch_size:
        Number of molecules to process per batch.

    Returns
    -------
    Total number of SIMILAR_TO edges created.
    """
    distance_threshold = 1.0 - threshold  # Jaccard distance = 1 - Tanimoto
    total = 0
    offset = 0

    # Get total molecule count for progress tracking
    with engine.connect() as count_conn:
        mol_total = count_conn.execute(
            text("SELECT count(*) FROM chem.molecules WHERE fp_morgan IS NOT NULL")
        ).scalar() or 0

    with age_connection(engine) as conn:
        while offset < mol_total:
            # Find similar pairs using pgvector KNN.
            # The inner LATERAL uses ORDER BY distance to leverage HNSW index,
            # then the outer WHERE deduplicates (keep ik_a < ik_b only).
            pairs = conn.execute(
                text("""
                    SELECT m1.inchikey AS ik_a, nn.inchikey AS ik_b,
                           ROUND((1 - (m1.fp_morgan <%> nn.fp_morgan))::numeric, 4) AS tanimoto
                    FROM (
                        SELECT inchikey, fp_morgan
                        FROM chem.molecules
                        WHERE fp_morgan IS NOT NULL
                        ORDER BY inchikey
                        LIMIT :batch_size OFFSET :offset
                    ) m1
                    CROSS JOIN LATERAL (
                        SELECT m2.inchikey, m2.fp_morgan
                        FROM chem.molecules m2
                        WHERE m2.fp_morgan IS NOT NULL
                          AND m2.inchikey != m1.inchikey
                        ORDER BY m1.fp_morgan <%> m2.fp_morgan
                        LIMIT 50
                    ) nn
                    WHERE nn.inchikey > m1.inchikey
                      AND (1 - (m1.fp_morgan <%> nn.fp_morgan)) >= :threshold
                """),
                {
                    "batch_size": batch_size,
                    "offset": offset,
                    "threshold": threshold,
                },
            ).fetchall()

            offset += batch_size

            if not pairs:
                log.info("similar_to_batch", pairs=0, offset=offset)
                continue

            # Create SIMILAR_TO edges in AGE
            maps = []
            for row in pairs:
                maps.append(
                    _format_agtype_map(
                        {
                            "ik_a": row.ik_a,
                            "ik_b": row.ik_b,
                            "tanimoto": float(row.tanimoto),
                        }
                    )
                )

            array_literal = "[" + ", ".join(maps) + "]"
            cypher = f"""
                UNWIND {array_literal} AS pair
                MATCH (a:Molecule {{inchikey: pair.ik_a}}),
                      (b:Molecule {{inchikey: pair.ik_b}})
                CREATE (a)-[:SIMILAR_TO {{tanimoto: pair.tanimoto}}]->(b)
                RETURN count(*) AS cnt
            """
            result = age_execute(conn, cypher, [("cnt", "agtype")])
            conn.commit()

            created = result[0]["cnt"] if result else 0
            total += created
            log.info("similar_to_batch", pairs=len(pairs), created=created, total=total)

    log.info("similar_to_complete", total=total)
    return total


# ---------------------------------------------------------------------------
# PRECURSOR_OF edges
# ---------------------------------------------------------------------------


def materialise_precursor_of(
    engine: Engine,
    max_depth: int = 3,
    batch_size: int = 5000,
    timeout_seconds: int = 120,
) -> int:
    """Create PRECURSOR_OF shortcut edges for multi-step synthesis paths.

    For each depth from 2 to ``max_depth``, finds paths of the form::

        (precursor)-[:REACTANT_IN]->(r1)-[:PRODUCT_OF]->(m1)
           ... repeated N times ...
        -[:REACTANT_IN]->(rN)-[:PRODUCT_OF]->(target)

    and creates a direct ``(precursor)-[:PRECURSOR_OF]->(target)`` edge
    with ``step_count`` and ``cumulative_yield`` properties.

    Parameters
    ----------
    engine:
        SQLAlchemy engine.
    max_depth:
        Maximum number of reaction steps (default 3, max 4).
        Higher depths cause combinatorial explosion.
    batch_size:
        Maximum paths to process per depth-query execution.
    timeout_seconds:
        Per-query statement timeout in seconds.
    """
    # Cap depth to prevent runaway queries
    max_depth = min(max_depth, 4)
    total = 0

    with age_connection(engine) as conn:
        # Set statement timeout to prevent combinatorial explosion
        conn.execute(text(f"SET statement_timeout = '{timeout_seconds}s'"))

        for depth in range(2, max_depth + 1):
            try:
                count = _materialise_precursor_at_depth(conn, depth, batch_size)
            except Exception as exc:
                log.warning(
                    "precursor_of_depth_failed",
                    depth=depth,
                    error=str(exc),
                )
                conn.rollback()
                continue
            total += count
            log.info("precursor_of_depth", depth=depth, edges=count, total=total)

        # Reset timeout
        conn.execute(text("SET statement_timeout = '0'"))

    log.info("precursor_of_complete", total=total)
    return total


def _materialise_precursor_at_depth(
    conn: Connection,
    depth: int,
    batch_size: int,
) -> int:
    """Create PRECURSOR_OF edges for a specific path depth."""

    cypher = _build_precursor_query(depth, batch_size)
    columns = [
        ("precursor_ik", "agtype"),
        ("target_ik", "agtype"),
        ("cum_yield", "agtype"),
    ]

    rows = age_execute(conn, cypher, columns)

    if not rows:
        return 0

    # Create shortcut edges
    maps: list[str] = []
    seen: set[tuple[str, str]] = set()

    for row in rows:
        precursor_ik = str(row["precursor_ik"])
        target_ik = str(row["target_ik"])
        cum_yield = row["cum_yield"]

        if precursor_ik == target_ik:
            continue  # Skip cycles

        pair = (precursor_ik, target_ik)
        if pair in seen:
            continue  # Deduplicate
        seen.add(pair)

        edge_data: dict[str, Any] = {
            "precursor_ik": precursor_ik,
            "target_ik": target_ik,
            "step_count": depth,
        }
        if cum_yield is not None:
            edge_data["cumulative_yield"] = round(float(cum_yield), 2)

        maps.append(_format_agtype_map(edge_data))

    if not maps:
        return 0

    # Batch the edge creation
    created = 0
    for i in range(0, len(maps), batch_size):
        chunk = maps[i : i + batch_size]
        array_literal = "[" + ", ".join(chunk) + "]"

        create_cypher = f"""
            UNWIND {array_literal} AS p
            MATCH (a:Molecule {{inchikey: p.precursor_ik}}),
                  (b:Molecule {{inchikey: p.target_ik}})
            CREATE (a)-[:PRECURSOR_OF {{
                step_count: p.step_count,
                cumulative_yield: p.cumulative_yield
            }}]->(b)
            RETURN count(*) AS cnt
        """
        result = age_execute(conn, create_cypher, [("cnt", "agtype")])
        conn.commit()
        created += result[0]["cnt"] if result else 0

    return created


def _build_precursor_query(depth: int, limit: int) -> str:
    """Build a Cypher query to find precursor paths at a given depth.

    Includes cycle prevention: all intermediate molecules must be distinct
    from precursor, target, and each other.
    """
    parts = ["MATCH (precursor:Molecule)"]

    yield_vars: list[str] = []
    intermediate_vars: list[str] = []

    for i in range(1, depth + 1):
        rxn_var = f"r{i}"
        yield_vars.append(f"{rxn_var}.yield_pct")

        if i < depth:
            mol_var = f"m{i}"
            intermediate_vars.append(mol_var)
            parts.append(
                f"-[:REACTANT_IN]->({rxn_var}:Reaction)"
                f"-[:PRODUCT_OF]->({mol_var}:Molecule)"
            )
        else:
            parts.append(
                f"-[:REACTANT_IN]->({rxn_var}:Reaction)"
                f"-[:PRODUCT_OF]->(target:Molecule)"
            )

    match_clause = "\n    ".join(parts)

    # Build WHERE clause: prevent cycles
    where_parts = ["precursor <> target"]
    for var in intermediate_vars:
        where_parts.append(f"precursor <> {var}")
        where_parts.append(f"target <> {var}")
    # Ensure intermediates are distinct from each other
    for i in range(len(intermediate_vars)):
        for j in range(i + 1, len(intermediate_vars)):
            where_parts.append(f"{intermediate_vars[i]} <> {intermediate_vars[j]}")

    where_clause = " AND ".join(where_parts)

    # Cumulative yield expression
    null_checks = " AND ".join(f"{v} IS NOT NULL" for v in yield_vars)
    product = " * ".join(yield_vars)
    divisor = 100 ** (depth - 1)

    yield_expr = (
        f"CASE WHEN {null_checks} "
        f"THEN {product} / {divisor}.0 "
        f"ELSE null END"
    )

    return (
        f"{match_clause}\n"
        f"WHERE {where_clause}\n"
        f"RETURN precursor.inchikey AS precursor_ik,\n"
        f"       target.inchikey AS target_ik,\n"
        f"       {yield_expr} AS cum_yield\n"
        f"LIMIT {limit}"
    )


# ---------------------------------------------------------------------------
# HAS_HAZARD edges
# ---------------------------------------------------------------------------


def materialise_has_hazard(
    engine: Engine,
    batch_size: int = 5000,
) -> int:
    """Create HAS_HAZARD property on Molecule nodes from onto.hazard_data.

    Sets ``signal_word`` and ``ghs_codes`` properties directly on Molecule
    nodes that have GHS hazard data. This avoids creating a separate node
    type and keeps the graph simple for queries.

    Returns the number of molecules updated.
    """
    total = 0
    offset = 0

    with age_connection(engine) as conn:
        # Count hazard records
        hazard_count = conn.execute(
            text("SELECT count(*) FROM onto.hazard_data")
        ).scalar() or 0

        if hazard_count == 0:
            log.info("has_hazard_skipped", reason="no hazard data")
            return 0

        while offset < hazard_count:
            rows = conn.execute(
                text("""
                    SELECT h.inchikey, h.signal_word,
                           array_to_string(h.ghs_codes, ',') AS ghs_codes_str
                    FROM onto.hazard_data h
                    ORDER BY h.inchikey
                    LIMIT :batch_size OFFSET :offset
                """),
                {"batch_size": batch_size, "offset": offset},
            ).fetchall()

            offset += batch_size

            if not rows:
                continue

            # Update Molecule nodes with hazard properties
            maps = []
            for row in rows:
                maps.append(
                    _format_agtype_map(
                        {
                            "ik": row.inchikey,
                            "signal_word": row.signal_word or "Unknown",
                            "ghs_codes": row.ghs_codes_str or "",
                        }
                    )
                )

            array_literal = "[" + ", ".join(maps) + "]"
            cypher = f"""
                UNWIND {array_literal} AS h
                MATCH (m:Molecule {{inchikey: h.ik}})
                SET m.signal_word = h.signal_word,
                    m.ghs_codes = h.ghs_codes
                RETURN count(*) AS cnt
            """
            result = age_execute(conn, cypher, [("cnt", "agtype")])
            conn.commit()

            updated = result[0]["cnt"] if result else 0
            total += updated
            log.info("has_hazard_batch", rows=len(rows), updated=updated, total=total)

    log.info("has_hazard_complete", total=total)
    return total
