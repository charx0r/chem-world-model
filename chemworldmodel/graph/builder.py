"""Build the Apache AGE property graph from relational tables.

Reads molecules, reactions, and reaction_components from PostgreSQL
and creates corresponding vertices and edges in the ``chemworld`` AGE graph
using UNWIND-based bulk loading.
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

# Role → (edge_label, property_keys)
_EDGE_ROLES: dict[str, tuple[str, list[str]]] = {
    "reactant": ("REACTANT_IN", ["stoichiometry", "equivalents"]),
    "product": ("PRODUCT_OF", ["yield_pct", "is_major"]),
    "catalyst": ("CATALYSES", ["equivalents"]),
    "solvent": ("SOLVENT_IN", ["volume_ml"]),
}

# Roles where the edge direction is (Reaction)-[]->(Molecule) instead of the default
# (Molecule)-[]->(Reaction)
_REVERSE_EDGE_ROLES = {"product"}


def build_graph(
    engine: Engine,
    batch_size: int = 5000,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Populate the AGE graph from relational tables.

    Parameters
    ----------
    engine:
        SQLAlchemy engine connected to the chemworldmodel database.
    batch_size:
        Number of rows to process per UNWIND batch.
    rebuild:
        If True, clear all existing graph data before building.

    Returns
    -------
    dict with keys: ``molecules``, ``reactions``, ``edges`` (dict of label→count).
    """
    with age_connection(engine) as conn:
        if rebuild:
            log.info("graph_clear_start")
            _clear_graph(conn)
            conn.commit()
            log.info("graph_clear_done")

        log.info("graph_build_start", batch_size=batch_size)

        mol_count = _build_molecule_nodes(conn, batch_size)
        rxn_count = _build_reaction_nodes(conn, batch_size)
        edge_counts = _build_edges(conn, batch_size)

        stats = {
            "molecules": mol_count,
            "reactions": rxn_count,
            "edges": edge_counts,
        }
        log.info("graph_build_complete", **stats)
        return stats


def _clear_graph(conn: Connection) -> None:
    """Remove all vertices and edges from the chemworld graph."""
    age_execute(
        conn,
        "MATCH (n) DETACH DELETE n RETURN count(n) AS cnt",
        [("cnt", "agtype")],
    )


def _build_molecule_nodes(conn: Connection, batch_size: int) -> int:
    """Create :Molecule vertices from chem.molecules."""
    total = 0
    offset = 0

    while True:
        rows = conn.execute(
            text("""
                SELECT inchikey, canonical_smiles, mol_formula, mol_weight,
                       commercially_available
                FROM chem.molecules
                ORDER BY inchikey
                LIMIT :limit OFFSET :offset
            """),
            {"limit": batch_size, "offset": offset},
        ).fetchall()

        if not rows:
            break

        maps = []
        for row in rows:
            maps.append(
                _format_agtype_map(
                    {
                        "inchikey": row.inchikey,
                        "smiles": row.canonical_smiles,
                        "mol_formula": row.mol_formula,
                        "mol_weight": row.mol_weight,
                        "commercially_available": row.commercially_available
                        if row.commercially_available is not None
                        else False,
                    }
                )
            )

        array_literal = "[" + ", ".join(maps) + "]"
        cypher = f"""
            UNWIND {array_literal} AS mol
            CREATE (:Molecule {{
                inchikey: mol.inchikey,
                smiles: mol.smiles,
                mol_formula: mol.mol_formula,
                mol_weight: mol.mol_weight,
                commercially_available: mol.commercially_available
            }})
            RETURN count(*) AS cnt
        """
        result = age_execute(conn, cypher, [("cnt", "agtype")])
        conn.commit()

        created = result[0]["cnt"] if result else 0
        total += created
        offset += batch_size
        log.info("molecule_nodes_batch", batch=len(rows), created=created, total=total)

    log.info("molecule_nodes_complete", total=total)
    return total


def _build_reaction_nodes(conn: Connection, batch_size: int) -> int:
    """Create :Reaction vertices from rxn.reactions."""
    total = 0
    offset = 0

    while True:
        rows = conn.execute(
            text("""
                SELECT reaction_id, reaction_class, temperature_c, yield_pct, source
                FROM rxn.reactions
                ORDER BY reaction_id
                LIMIT :limit OFFSET :offset
            """),
            {"limit": batch_size, "offset": offset},
        ).fetchall()

        if not rows:
            break

        maps = []
        for row in rows:
            maps.append(
                _format_agtype_map(
                    {
                        "reaction_id": row.reaction_id,
                        "reaction_class": row.reaction_class,
                        "temperature_c": row.temperature_c,
                        "yield_pct": row.yield_pct,
                        "source": row.source,
                    }
                )
            )

        array_literal = "[" + ", ".join(maps) + "]"
        cypher = f"""
            UNWIND {array_literal} AS rxn
            CREATE (:Reaction {{
                reaction_id: rxn.reaction_id,
                reaction_class: rxn.reaction_class,
                temperature_c: rxn.temperature_c,
                yield_pct: rxn.yield_pct,
                source: rxn.source
            }})
            RETURN count(*) AS cnt
        """
        result = age_execute(conn, cypher, [("cnt", "agtype")])
        conn.commit()

        created = result[0]["cnt"] if result else 0
        total += created
        offset += batch_size
        log.info("reaction_nodes_batch", batch=len(rows), created=created, total=total)

    log.info("reaction_nodes_complete", total=total)
    return total


def _build_edges(conn: Connection, batch_size: int) -> dict[str, int]:
    """Create edges from rxn.reaction_components, grouped by role."""
    edge_counts: dict[str, int] = {}

    for role, (label, prop_keys) in _EDGE_ROLES.items():
        count = _build_edges_for_role(conn, role, label, prop_keys, batch_size)
        edge_counts[label] = count

    log.info("edges_complete", **edge_counts)
    return edge_counts


def _build_edges_for_role(
    conn: Connection,
    role: str,
    label: str,
    prop_keys: list[str],
    batch_size: int,
) -> int:
    """Create edges for a specific reaction component role."""
    total = 0
    offset = 0

    # Validate column names are safe identifiers
    safe_cols = ["reaction_id", "inchikey"] + prop_keys
    for col in safe_cols:
        assert col.isidentifier(), f"Unsafe column name: {col}"
    col_list = ", ".join(safe_cols)

    while True:
        rows = conn.execute(
            text(f"""
                SELECT {col_list}
                FROM rxn.reaction_components
                WHERE role = :role
                ORDER BY id
                LIMIT :limit OFFSET :offset
            """),
            {"role": role, "limit": batch_size, "offset": offset},
        ).fetchall()

        if not rows:
            break

        maps = []
        for row in rows:
            edge_data: dict[str, Any] = {
                "mol_ik": row.inchikey,
                "rxn_id": row.reaction_id,
            }
            for key in prop_keys:
                edge_data[key] = getattr(row, key)
            maps.append(_format_agtype_map(edge_data))

        array_literal = "[" + ", ".join(maps) + "]"

        # Build edge property assignment
        prop_assignments = ", ".join(f"{k}: e.{k}" for k in prop_keys)
        prop_clause = f" {{{prop_assignments}}}" if prop_assignments else ""

        if role in _REVERSE_EDGE_ROLES:
            # (Reaction)-[:PRODUCT_OF]->(Molecule)
            cypher = f"""
                UNWIND {array_literal} AS e
                MATCH (r:Reaction {{reaction_id: e.rxn_id}}),
                      (m:Molecule {{inchikey: e.mol_ik}})
                CREATE (r)-[:{label}{prop_clause}]->(m)
                RETURN count(*) AS cnt
            """
        else:
            # (Molecule)-[:REACTANT_IN]->(Reaction)
            cypher = f"""
                UNWIND {array_literal} AS e
                MATCH (m:Molecule {{inchikey: e.mol_ik}}),
                      (r:Reaction {{reaction_id: e.rxn_id}})
                CREATE (m)-[:{label}{prop_clause}]->(r)
                RETURN count(*) AS cnt
            """

        result = age_execute(conn, cypher, [("cnt", "agtype")])
        conn.commit()

        created = result[0]["cnt"] if result else 0
        if created < len(rows):
            log.warning(
                "edges_missing_nodes",
                label=label,
                expected=len(rows),
                created=created,
            )

        total += created
        offset += batch_size
        log.info("edges_batch", label=label, batch=len(rows), created=created, total=total)

    log.info(f"edges_{label}_complete", total=total)
    return total
