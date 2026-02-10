"""Retrosynthetic route finding via Apache AGE Cypher queries.

Searches for synthesis paths from commercially available starting materials
to a target molecule, traversing the bipartite Molecule↔Reaction graph.
Uses fixed-depth queries (1–4 reaction steps) for AGE compatibility.
"""

from __future__ import annotations

import structlog
from sqlalchemy import Engine

from chemworldmodel.graph import age_connection, age_execute
from chemworldmodel.models.graph import (
    GraphStats,
    ReactionStep,
    RouteNode,
    RouteSearchResult,
    SynthesisRoute,
)

log = structlog.get_logger()


def find_routes(
    target_inchikey: str,
    engine: Engine,
    max_depth: int = 8,
    max_routes: int = 10,
) -> RouteSearchResult:
    """Find synthesis routes from commercially available starting materials.

    Searches shortest routes first (1-step, then 2-step, etc.) and stops
    early once ``max_routes`` are found.

    Parameters
    ----------
    target_inchikey:
        InChIKey of the target molecule.
    engine:
        SQLAlchemy engine.
    max_depth:
        Maximum number of graph hops (each reaction step = 2 hops).
        Default 8 = up to 4 reaction steps.
    max_routes:
        Maximum number of routes to return.
    """
    max_steps = max_depth // 2
    all_routes: list[SynthesisRoute] = []

    with age_connection(engine) as conn:
        for depth in range(1, max_steps + 1):
            remaining = max_routes - len(all_routes)
            if remaining <= 0:
                break

            cypher = _build_route_query(target_inchikey, depth, remaining)
            columns = _route_columns(depth)
            rows = age_execute(conn, cypher, columns)

            for row in rows:
                route = _parse_route_row(row, depth)
                if route is not None:
                    all_routes.append(route)

            log.info(
                "route_search_depth",
                depth=depth,
                found=len(rows),
                total=len(all_routes),
            )

    return RouteSearchResult(
        target_inchikey=target_inchikey,
        routes=all_routes[:max_routes],
        route_count=len(all_routes[:max_routes]),
        search_depth=max_steps,
    )


def _build_route_query(target_inchikey: str, depth: int, limit: int) -> str:
    """Generate a fixed-depth Cypher query for exactly ``depth`` reaction steps.

    Each step is: ``(Molecule)-[:REACTANT_IN]->(Reaction)-[:PRODUCT_OF]->(Molecule)``

    For depth=1:
        MATCH (s:Molecule {commercially_available: true})
            -[:REACTANT_IN]->(r1:Reaction)-[:PRODUCT_OF]->(t:Molecule {inchikey: '...'})

    For depth=2:
        MATCH (s:Molecule {commercially_available: true})
            -[:REACTANT_IN]->(r1:Reaction)-[:PRODUCT_OF]->(m1:Molecule)
            -[:REACTANT_IN]->(r2:Reaction)-[:PRODUCT_OF]->(t:Molecule {inchikey: '...'})
    """
    # Validate InChIKey format strictly to prevent Cypher injection
    from chemworldmodel.graph import INCHIKEY_RE

    if not INCHIKEY_RE.match(target_inchikey):
        raise ValueError(f"Invalid InChIKey format: {target_inchikey!r}")
    ik = target_inchikey

    parts = [
        f"MATCH (s:Molecule {{commercially_available: true}})"
    ]

    # Build the chain of reaction steps
    for i in range(1, depth + 1):
        rxn_var = f"r{i}"
        if i < depth:
            mol_var = f"m{i}"
            parts.append(
                f"-[:REACTANT_IN]->({rxn_var}:Reaction)"
                f"-[:PRODUCT_OF]->({mol_var}:Molecule)"
            )
        else:
            # Last step targets the target molecule
            parts.append(
                f"-[:REACTANT_IN]->({rxn_var}:Reaction)"
                f"-[:PRODUCT_OF]->(t:Molecule {{inchikey: '{ik}'}})"
            )

    match_clause = "\n    ".join(parts)

    # Build RETURN clause
    return_items = [
        "s.inchikey AS start_ik",
        "s.smiles AS start_smiles",
        "s.commercially_available AS start_avail",
    ]

    for i in range(1, depth + 1):
        return_items.extend([
            f"r{i}.reaction_id AS r{i}_id",
            f"r{i}.reaction_class AS r{i}_class",
            f"r{i}.yield_pct AS r{i}_yield",
        ])
        if i < depth:
            return_items.extend([
                f"m{i}.inchikey AS m{i}_ik",
                f"m{i}.smiles AS m{i}_smiles",
            ])

    return_items.extend([
        "t.inchikey AS target_ik",
        "t.smiles AS target_smiles",
    ])

    return_clause = ", ".join(return_items)

    return f"{match_clause}\nRETURN {return_clause}\nLIMIT {limit}"


def _route_columns(depth: int) -> list[tuple[str, str]]:
    """Build the column definitions for a route query at a given depth."""
    cols: list[tuple[str, str]] = [
        ("start_ik", "agtype"),
        ("start_smiles", "agtype"),
        ("start_avail", "agtype"),
    ]

    for i in range(1, depth + 1):
        cols.extend([
            (f"r{i}_id", "agtype"),
            (f"r{i}_class", "agtype"),
            (f"r{i}_yield", "agtype"),
        ])
        if i < depth:
            cols.extend([
                (f"m{i}_ik", "agtype"),
                (f"m{i}_smiles", "agtype"),
            ])

    cols.extend([
        ("target_ik", "agtype"),
        ("target_smiles", "agtype"),
    ])

    return cols


def _parse_route_row(row: dict, depth: int) -> SynthesisRoute | None:
    """Parse a single row from a route query into a SynthesisRoute."""
    try:
        start = RouteNode(
            inchikey=str(row["start_ik"]),
            smiles=str(row["start_smiles"]) if row["start_smiles"] else None,
            commercially_available=True,
        )

        target = RouteNode(
            inchikey=str(row["target_ik"]),
            smiles=str(row["target_smiles"]) if row["target_smiles"] else None,
        )

        steps: list[ReactionStep] = []
        yields: list[float] = []

        for i in range(1, depth + 1):
            rxn_id = str(row[f"r{i}_id"])
            rxn_class = row.get(f"r{i}_class")
            yield_pct = row.get(f"r{i}_yield")

            steps.append(
                ReactionStep(
                    reaction_id=rxn_id,
                    reaction_class=str(rxn_class) if rxn_class else None,
                    yield_pct=float(yield_pct) if yield_pct is not None else None,
                )
            )
            if yield_pct is not None:
                yields.append(float(yield_pct))

        # Cumulative yield: product of all step yields / 100^(n-1)
        cumulative_yield = None
        if len(yields) == depth and all(y > 0 for y in yields):
            cum = yields[0]
            for y in yields[1:]:
                cum = cum * y / 100.0
            cumulative_yield = round(cum, 2)

        return SynthesisRoute(
            target=target,
            starting_materials=[start],
            steps=steps,
            step_count=depth,
            cumulative_yield=cumulative_yield,
        )
    except (KeyError, ValueError, TypeError) as exc:
        log.warning("route_parse_error", error=str(exc), row=row)
        return None


def get_graph_stats(engine: Engine) -> GraphStats:
    """Return node and edge counts for the chemworld graph."""
    with age_connection(engine) as conn:
        # Count molecule nodes
        mol_rows = age_execute(
            conn,
            "MATCH (m:Molecule) RETURN count(m) AS cnt",
            [("cnt", "agtype")],
        )
        mol_count = int(mol_rows[0]["cnt"]) if mol_rows else 0

        # Count reaction nodes
        rxn_rows = age_execute(
            conn,
            "MATCH (r:Reaction) RETURN count(r) AS cnt",
            [("cnt", "agtype")],
        )
        rxn_count = int(rxn_rows[0]["cnt"]) if rxn_rows else 0

        # Count edges by label
        edge_counts: dict[str, int] = {}
        for label in [
            "REACTANT_IN",
            "PRODUCT_OF",
            "CATALYSES",
            "SOLVENT_IN",
            "SIMILAR_TO",
            "PRECURSOR_OF",
        ]:
            rows = age_execute(
                conn,
                f"MATCH ()-[e:{label}]->() RETURN count(e) AS cnt",
                [("cnt", "agtype")],
            )
            cnt = int(rows[0]["cnt"]) if rows else 0
            if cnt > 0:
                edge_counts[label] = cnt

    return GraphStats(
        molecule_count=mol_count,
        reaction_count=rxn_count,
        edge_counts=edge_counts,
    )
