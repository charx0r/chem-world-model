"""Apache AGE graph helpers for ChemWorldModel.

Provides connection setup, Cypher execution, and agtype parsing
using raw psycopg3 (no apache-age-python dependency).

Every AGE connection requires:
  1. LOAD 'age'
  2. SET search_path = ag_catalog, "$user", public
"""

from __future__ import annotations

import json
import math
import re
from contextlib import contextmanager
from typing import Any, Generator

import structlog
from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

log = structlog.get_logger()

# Regex to strip AGE type suffixes from agtype values
_AGTYPE_SUFFIX = re.compile(r"::(vertex|edge|path|numeric)$")

# Regex for individual elements inside a path array — uses a greedy match
# anchored to the ::type suffix to correctly handle nested JSON braces.
_PATH_ELEMENT = re.compile(
    r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})::(vertex|edge)",
)


def parse_agtype(value: Any) -> Any:
    """Parse an AGE agtype value into a Python object.

    AGE returns results as the ``agtype`` PostgreSQL type.  When read via
    psycopg3 these arrive as Python strings with a type suffix:

    - Vertex: ``{"id": 1, ...}::vertex``
    - Edge:   ``{"id": 2, ...}::edge``
    - Path:   ``[{"id":1,...}::vertex, {"id":2,...}::edge, ...]::path``
    - Scalar: ``123``, ``"hello"``, ``true``, ``null``
    """
    if value is None:
        return None

    if not isinstance(value, str):
        return value

    s = value.strip()

    # Path: "[...]::path"
    if s.endswith("::path"):
        inner = s[: -len("::path")].strip()
        if inner.startswith("[") and inner.endswith("]"):
            elements = []
            for m in _PATH_ELEMENT.finditer(inner):
                obj = json.loads(m.group(1))
                obj["_type"] = m.group(2)
                elements.append(obj)
            return elements
        return json.loads(inner)

    # Vertex or edge: "{...}::vertex" / "{...}::edge"
    m = _AGTYPE_SUFFIX.search(s)
    if m:
        type_label = m.group(1)
        json_str = s[: m.start()].strip()
        try:
            obj = json.loads(json_str)
            if isinstance(obj, dict):
                obj["_type"] = type_label
            return obj
        except json.JSONDecodeError:
            return s

    # Bare JSON (object, array, string, number, boolean, null)
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return s


# Strict identifier pattern for graph names and column names
_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Valid InChIKey format: 14 uppercase letters, hyphen, 10 uppercase letters, hyphen, 1 uppercase letter
INCHIKEY_RE = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")


@contextmanager
def age_connection(engine: Engine) -> Generator[Connection, None, None]:
    """Context manager that sets up AGE on a SQLAlchemy connection.

    Loads the AGE shared library and configures the search path so that
    ``cypher()`` function calls resolve correctly.
    """
    with engine.connect() as conn:
        try:
            conn.execute(text("LOAD 'age'"))
        except Exception as e:
            raise RuntimeError(
                "Failed to load AGE extension. Ensure it is installed: "
                "CREATE EXTENSION IF NOT EXISTS age CASCADE"
            ) from e
        conn.execute(text("SET search_path = ag_catalog, \"$user\", public"))
        yield conn


def age_execute(
    conn: Connection,
    cypher: str,
    columns: list[tuple[str, str]],
    *,
    graph_name: str = "chemworld",
) -> list[dict[str, Any]]:
    """Execute a Cypher query via AGE and return parsed results.

    Parameters
    ----------
    conn:
        A SQLAlchemy connection already set up via :func:`age_connection`.
    cypher:
        The openCypher query string.  Must contain a RETURN clause —
        AGE requires the column list to match the RETURN output.
    columns:
        List of ``(name, pg_type)`` tuples defining the output columns.
        Example: ``[("v", "agtype"), ("count", "agtype")]``
    graph_name:
        The AGE graph name (default ``"chemworld"``).

    Returns
    -------
    list[dict[str, Any]]
        Each row as a dict with column names as keys, agtype values parsed.
    """
    # Validate graph_name and column identifiers to prevent SQL injection
    if not _IDENTIFIER_RE.match(graph_name):
        raise ValueError(f"Invalid graph name: {graph_name!r}")
    for name, pg_type in columns:
        if not _IDENTIFIER_RE.match(name):
            raise ValueError(f"Invalid column name: {name!r}")
        if not _IDENTIFIER_RE.match(pg_type):
            raise ValueError(f"Invalid PG type: {pg_type!r}")

    col_defs = ", ".join(f"{name} {pg_type}" for name, pg_type in columns)
    sql = f"SELECT * FROM cypher('{graph_name}', $$ {cypher} $$) AS ({col_defs})"

    # Use exec_driver_sql to bypass SQLAlchemy's bind-parameter parsing,
    # which conflicts with Cypher's :Label syntax
    result = conn.exec_driver_sql(sql)
    rows = []
    for row in result:
        parsed = {}
        for i, (name, _) in enumerate(columns):
            parsed[name] = parse_agtype(row[i])
        rows.append(parsed)
    return rows


def _format_agtype_value(value: Any) -> str:
    """Format a Python value as an AGE Cypher literal.

    Used when building UNWIND arrays for bulk loading.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return "null"
        return str(value)
    if isinstance(value, str):
        # Escape for Cypher single-quoted string literals
        escaped = (
            value.replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f"'{escaped}'"
    return str(value)


def _format_agtype_map(d: dict[str, Any]) -> str:
    """Format a Python dict as an AGE Cypher map literal ``{key: value, ...}``."""
    pairs = []
    for k, v in d.items():
        pairs.append(f"{k}: {_format_agtype_value(v)}")
    return "{" + ", ".join(pairs) + "}"
