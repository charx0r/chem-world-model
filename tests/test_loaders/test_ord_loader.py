"""Tests for the ORD loader — compound parsing, role mapping, descriptors."""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import inchi as rdinchi

from chemworldmodel.loaders.ord_loader import (
    _ROLE_MAP,
    _extract_amounts,
    _extract_temperature,
    _parse_compound,
)
from ord_schema.proto import reaction_pb2


# ---------------------------------------------------------------------------
# Compound parsing
# ---------------------------------------------------------------------------


class TestParseCompound:
    def _make_compound(self, smiles: str | None = None, inchi: str | None = None):
        """Helper to create a minimal Compound protobuf."""
        compound = reaction_pb2.Compound()
        if smiles:
            ident = compound.identifiers.add()
            ident.type = reaction_pb2.CompoundIdentifier.SMILES
            ident.value = smiles
        if inchi:
            ident = compound.identifiers.add()
            ident.type = reaction_pb2.CompoundIdentifier.INCHI
            ident.value = inchi
        return compound

    def test_valid_smiles(self):
        compound = self._make_compound(smiles="c1ccccc1")
        result = _parse_compound(compound)
        assert result is not None
        inchikey, mol_row = result
        assert inchikey is not None
        assert len(inchikey) == 27  # InChIKey is always 27 chars
        assert mol_row["canonical_smiles"] == "c1ccccc1"
        assert mol_row["mol_formula"] == "C6H6"
        assert mol_row["mol_weight"] > 0

    def test_valid_inchi_fallback(self):
        # Benzene InChI
        compound = self._make_compound(inchi="InChI=1S/C6H6/c1-2-4-6-5-3-1/h1-6H")
        result = _parse_compound(compound)
        assert result is not None
        inchikey, mol_row = result
        assert mol_row["canonical_smiles"] is not None

    def test_invalid_smiles_returns_none(self):
        compound = self._make_compound(smiles="not_a_molecule!!!")
        result = _parse_compound(compound)
        assert result is None

    def test_no_identifiers_returns_none(self):
        compound = reaction_pb2.Compound()
        result = _parse_compound(compound)
        assert result is None

    def test_descriptors_computed(self):
        compound = self._make_compound(smiles="CCO")  # ethanol
        result = _parse_compound(compound)
        assert result is not None
        _, mol_row = result
        assert mol_row["hba"] >= 0
        assert mol_row["hbd"] >= 0
        assert mol_row["num_rotatable"] >= 0
        assert mol_row["num_rings"] == 0
        assert mol_row["logp"] is not None
        assert mol_row["tpsa"] is not None

    def test_deduplication_same_inchikey(self):
        # Two different SMILES representations of the same molecule
        c1 = self._make_compound(smiles="OCC")  # ethanol
        c2 = self._make_compound(smiles="CCO")  # ethanol (canonical)
        r1 = _parse_compound(c1)
        r2 = _parse_compound(c2)
        assert r1 is not None and r2 is not None
        assert r1[0] == r2[0]  # same InChIKey


# ---------------------------------------------------------------------------
# Role mapping
# ---------------------------------------------------------------------------


class TestRoleMapping:
    def test_all_mapped_roles_are_valid(self):
        valid_roles = {
            "reactant", "product", "catalyst", "solvent", "reagent",
            "base", "acid", "ligand", "additive", "internal_standard",
        }
        for enum_val, role_str in _ROLE_MAP.items():
            assert role_str in valid_roles, f"Mapped role '{role_str}' not in schema"

    def test_reactant_maps(self):
        assert _ROLE_MAP[reaction_pb2.ReactionRole.REACTANT] == "reactant"

    def test_product_maps(self):
        assert _ROLE_MAP[reaction_pb2.ReactionRole.PRODUCT] == "product"

    def test_catalyst_maps(self):
        assert _ROLE_MAP[reaction_pb2.ReactionRole.CATALYST] == "catalyst"


# ---------------------------------------------------------------------------
# Temperature extraction
# ---------------------------------------------------------------------------


class TestExtractTemperature:
    def _make_conditions(self, value: float, units: int):
        cond = reaction_pb2.ReactionConditions()
        cond.temperature.setpoint.value = value
        cond.temperature.setpoint.units = units
        return cond

    def test_celsius(self):
        cond = self._make_conditions(25.0, reaction_pb2.Temperature.CELSIUS)
        assert _extract_temperature(cond) == 25.0

    def test_kelvin_to_celsius(self):
        cond = self._make_conditions(373.15, reaction_pb2.Temperature.KELVIN)
        result = _extract_temperature(cond)
        assert result is not None
        assert abs(result - 100.0) < 0.1

    def test_fahrenheit_to_celsius(self):
        cond = self._make_conditions(212.0, reaction_pb2.Temperature.FAHRENHEIT)
        result = _extract_temperature(cond)
        assert result is not None
        assert abs(result - 100.0) < 0.1

    def test_no_temperature(self):
        cond = reaction_pb2.ReactionConditions()
        assert _extract_temperature(cond) is None


# ---------------------------------------------------------------------------
# Amount extraction
# ---------------------------------------------------------------------------


class TestExtractAmounts:
    def test_mass_in_grams(self):
        compound = reaction_pb2.Compound()
        compound.amount.mass.value = 5.0
        compound.amount.mass.units = reaction_pb2.Mass.GRAM
        mass_g, volume_ml, equiv = _extract_amounts(compound)
        assert mass_g == 5.0
        assert volume_ml is None

    def test_mass_in_milligrams(self):
        compound = reaction_pb2.Compound()
        compound.amount.mass.value = 500.0
        compound.amount.mass.units = reaction_pb2.Mass.MILLIGRAM
        mass_g, volume_ml, equiv = _extract_amounts(compound)
        assert mass_g is not None
        assert abs(mass_g - 0.5) < 0.001

    def test_volume_in_ml(self):
        compound = reaction_pb2.Compound()
        compound.amount.volume.value = 10.0
        compound.amount.volume.units = reaction_pb2.Volume.MILLILITER
        mass_g, volume_ml, equiv = _extract_amounts(compound)
        assert volume_ml == 10.0

    def test_no_amount(self):
        compound = reaction_pb2.Compound()
        mass_g, volume_ml, equiv = _extract_amounts(compound)
        assert mass_g is None
        assert volume_ml is None
        assert equiv is None
