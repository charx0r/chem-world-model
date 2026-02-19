"""Pydantic models for reaction API responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReactionComponent(BaseModel):
    inchikey: str
    canonical_smiles: str | None = None
    role: str
    equivalents: float | None = None
    mass_g: float | None = None
    volume_ml: float | None = None
    yield_pct: float | None = None


class ReactionCondition(BaseModel):
    condition_type: str
    value: float | None = None
    unit: str
    phase: str | None = None


class ReactionDetail(BaseModel):
    reaction_id: str
    reaction_smiles: str | None = None
    reaction_class: str | None = None
    temperature_c: float | None = None
    pressure_bar: float | None = None
    time_seconds: int | None = None
    atmosphere: str | None = None
    yield_pct: float | None = None
    yield_type: str | None = None
    selectivity: str | None = None
    source: str | None = None
    source_id: str | None = None
    doi: str | None = None
    patent_id: str | None = None
    components: list[ReactionComponent] = Field(default_factory=list)
    conditions: list[ReactionCondition] = Field(default_factory=list)


class ReactionSearchResult(BaseModel):
    reactions: list[ReactionDetail] = Field(default_factory=list)
    total: int
    offset: int
    limit: int
