"""Pydantic models for the NL-to-SQL query pipeline."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)


class QueryResult(BaseModel):
    answer: str
    sql: str
    citations: list[str] = Field(default_factory=list)
    reaction_count: int = 0
    statistics: dict[str, Any] = Field(default_factory=dict)
    raw_data: list[dict[str, Any]] = Field(default_factory=list)


class SimilarMolecule(BaseModel):
    inchikey: str
    canonical_smiles: str
    tanimoto: float


class LLMSQLResponse(BaseModel):
    """Structured output model for LLM SQL generation."""

    sql: str
    explanation: str
