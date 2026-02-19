"""Pydantic models for molecule API responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HazardInfo(BaseModel):
    ghs_codes: list[str] = Field(default_factory=list)
    signal_word: str | None = None
    pictograms: list[str] = Field(default_factory=list)
    source: str | None = None


class BioactivityInfo(BaseModel):
    target_name: str | None = None
    target_organism: str | None = None
    activity_type: str
    value: float | None = None
    unit: str | None = None


class ReactionSummary(BaseModel):
    """Compact reaction reference for molecule detail view."""

    reaction_id: str
    reaction_class: str | None = None
    role: str
    yield_pct: float | None = None


class MoleculeDetail(BaseModel):
    inchikey: str
    canonical_smiles: str
    iupac_name: str | None = None
    mol_formula: str | None = None
    mol_weight: float | None = None
    exact_mass: float | None = None
    logp: float | None = None
    tpsa: float | None = None
    hba: int | None = None
    hbd: int | None = None
    num_rotatable: int | None = None
    num_rings: int | None = None
    complexity: float | None = None
    pubchem_cid: int | None = None
    chembl_id: str | None = None
    chebi_id: str | None = None
    cas_number: str | None = None
    commercially_available: bool | None = None
    sources: list[str] = Field(default_factory=list)
    hazards: list[HazardInfo] = Field(default_factory=list)
    bioactivities: list[BioactivityInfo] = Field(default_factory=list)
    reactions: list[ReactionSummary] = Field(default_factory=list)
    similar: list[SimilarMoleculeHit] = Field(default_factory=list)


class SimilarMoleculeHit(BaseModel):
    inchikey: str
    canonical_smiles: str
    tanimoto: float


class MoleculeSearchResult(BaseModel):
    molecules: list[MoleculeDetail] = Field(default_factory=list)
    total: int
    offset: int
    limit: int


# Rebuild MoleculeDetail to resolve forward reference to SimilarMoleculeHit
MoleculeDetail.model_rebuild()
