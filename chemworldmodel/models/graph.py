"""Pydantic models for the Apache AGE graph layer."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReactionStep(BaseModel):
    """A single reaction step in a synthesis route."""

    reaction_id: str
    reaction_class: str | None = None
    yield_pct: float | None = None


class RouteNode(BaseModel):
    """A molecule node in a synthesis route."""

    inchikey: str
    smiles: str | None = None
    commercially_available: bool = False


class SynthesisRoute(BaseModel):
    """A complete synthesis route from starting materials to target."""

    target: RouteNode
    starting_materials: list[RouteNode]
    steps: list[ReactionStep]
    step_count: int
    cumulative_yield: float | None = None


class RouteSearchResult(BaseModel):
    """Result of a retrosynthetic route search."""

    target_inchikey: str
    routes: list[SynthesisRoute] = Field(default_factory=list)
    route_count: int = 0
    search_depth: int


class GraphStats(BaseModel):
    """Node and edge counts for the AGE graph."""

    molecule_count: int = 0
    reaction_count: int = 0
    edge_counts: dict[str, int] = Field(default_factory=dict)
