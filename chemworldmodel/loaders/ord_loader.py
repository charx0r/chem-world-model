"""ORD (Open Reaction Database) data loader.

Reads .pb.gz protobuf files from the ORD dataset, extracts reactions,
decomposes them into molecules and components, and bulk-inserts into
the relational schema.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Iterator

import structlog
from rdkit import Chem
from rdkit.Chem import Descriptors, Crippen, rdMolDescriptors, inchi as rdinchi
from sqlalchemy import Connection
from sqlalchemy.dialects.postgresql import insert as pg_insert

from chemworldmodel.db.schema import (
    molecules,
    molecule_provenance,
    reaction_components,
    reaction_conditions,
    reactions,
)
from chemworldmodel.loaders.base import BaseLoader, LoadStats

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# ORD protobuf imports
# ---------------------------------------------------------------------------
from ord_schema import message_helpers
from ord_schema.proto import dataset_pb2, reaction_pb2

# ---------------------------------------------------------------------------
# ORD ReactionRole enum → schema role string
# ---------------------------------------------------------------------------
_ROLE_MAP: dict[int, str] = {
    reaction_pb2.ReactionRole.REACTANT: "reactant",
    reaction_pb2.ReactionRole.REAGENT: "reagent",
    reaction_pb2.ReactionRole.SOLVENT: "solvent",
    reaction_pb2.ReactionRole.CATALYST: "catalyst",
    reaction_pb2.ReactionRole.INTERNAL_STANDARD: "internal_standard",
    reaction_pb2.ReactionRole.PRODUCT: "product",
    reaction_pb2.ReactionRole.BYPRODUCT: "product",
    reaction_pb2.ReactionRole.SIDE_PRODUCT: "product",
    reaction_pb2.ReactionRole.WORKUP: "additive",
}

# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------

# Temperature units → Celsius conversion
_TEMP_UNITS = {
    reaction_pb2.Temperature.CELSIUS: lambda v: v,
    reaction_pb2.Temperature.FAHRENHEIT: lambda v: (v - 32) * 5.0 / 9.0,
    reaction_pb2.Temperature.KELVIN: lambda v: v - 273.15,
}

# Pressure units → bar conversion
_PRESSURE_UNITS = {
    reaction_pb2.Pressure.BAR: lambda v: v,
    reaction_pb2.Pressure.ATMOSPHERE: lambda v: v * 1.01325,
    reaction_pb2.Pressure.PSI: lambda v: v * 0.0689476,
    reaction_pb2.Pressure.KPSI: lambda v: v * 68.9476,
    reaction_pb2.Pressure.KILOPASCAL: lambda v: v * 0.01,
    reaction_pb2.Pressure.PASCAL: lambda v: v * 1e-5,
    reaction_pb2.Pressure.MM_HG: lambda v: v * 0.00133322,
    reaction_pb2.Pressure.TORR: lambda v: v * 0.00133322,
}

# Mass units → grams
_MASS_UNITS = {
    reaction_pb2.Mass.KILOGRAM: lambda v: v * 1000.0,
    reaction_pb2.Mass.GRAM: lambda v: v,
    reaction_pb2.Mass.MILLIGRAM: lambda v: v * 0.001,
    reaction_pb2.Mass.MICROGRAM: lambda v: v * 1e-6,
}

# Volume units → millilitres
_VOLUME_UNITS = {
    reaction_pb2.Volume.LITER: lambda v: v * 1000.0,
    reaction_pb2.Volume.MILLILITER: lambda v: v,
    reaction_pb2.Volume.MICROLITER: lambda v: v * 0.001,
    reaction_pb2.Volume.NANOLITER: lambda v: v * 1e-6,
}

# Time units → seconds
_TIME_UNITS = {
    reaction_pb2.Time.HOUR: lambda v: v * 3600.0,
    reaction_pb2.Time.MINUTE: lambda v: v * 60.0,
    reaction_pb2.Time.SECOND: lambda v: v,
    reaction_pb2.Time.DAY: lambda v: v * 86400.0,
}

# Atmosphere enum → string
_ATMOSPHERE_MAP = {
    reaction_pb2.PressureConditions.Atmosphere.AIR: "air",
    reaction_pb2.PressureConditions.Atmosphere.NITROGEN: "nitrogen",
    reaction_pb2.PressureConditions.Atmosphere.ARGON: "argon",
    reaction_pb2.PressureConditions.Atmosphere.OXYGEN: "oxygen",
    reaction_pb2.PressureConditions.Atmosphere.HYDROGEN: "hydrogen",
    reaction_pb2.PressureConditions.Atmosphere.CARBON_MONOXIDE: "carbon_monoxide",
    reaction_pb2.PressureConditions.Atmosphere.CARBON_DIOXIDE: "carbon_dioxide",
    reaction_pb2.PressureConditions.Atmosphere.METHANE: "methane",
    reaction_pb2.PressureConditions.Atmosphere.AMMONIA: "ammonia",
    reaction_pb2.PressureConditions.Atmosphere.OZONE: "ozone",
    reaction_pb2.PressureConditions.Atmosphere.ETHYLENE: "ethylene",
    reaction_pb2.PressureConditions.Atmosphere.ACETYLENE: "acetylene",
}

# ProductMeasurement types
_YIELD_TYPE = reaction_pb2.ProductMeasurement.YIELD
_SELECTIVITY_TYPE = reaction_pb2.ProductMeasurement.SELECTIVITY


class ORDLoader(BaseLoader):
    """Load Open Reaction Database protobuf data into PostgreSQL."""

    source_name = "ord"

    def extract(self, **kwargs: Any) -> Iterator[reaction_pb2.Reaction]:
        """Yield individual Reaction messages from .pb.gz files."""
        data_dir = Path(kwargs["data_dir"])
        limit = kwargs.get("limit")
        count = 0

        pb_files = sorted(data_dir.glob("**/*.pb.gz"))
        self.log.info("found_pb_files", count=len(pb_files), data_dir=str(data_dir))

        for pb_file in pb_files:
            try:
                dataset = message_helpers.load_message(
                    str(pb_file), dataset_pb2.Dataset
                )
            except Exception as e:
                self.log.warning("dataset_load_error", file=str(pb_file), error=str(e))
                continue

            self.log.info(
                "processing_file",
                file=pb_file.name,
                reactions=len(dataset.reactions),
            )

            for rxn in dataset.reactions:
                yield rxn
                count += 1
                if limit and count >= limit:
                    self.log.info("limit_reached", limit=limit)
                    return

    def _get_item_id(self, raw_item: Any) -> str | None:
        if isinstance(raw_item, reaction_pb2.Reaction):
            return raw_item.reaction_id or None
        return None

    def transform_one(self, raw_item: Any) -> dict | None:
        """Transform a single ORD Reaction into a structured dict."""
        rxn: reaction_pb2.Reaction = raw_item
        reaction_id = rxn.reaction_id
        if not reaction_id:
            return None

        # Extract reaction SMILES from identifiers
        reaction_smiles = None
        for ident in rxn.identifiers:
            if ident.type == reaction_pb2.ReactionIdentifier.REACTION_SMILES:
                reaction_smiles = ident.value
                break
            if ident.type == reaction_pb2.ReactionIdentifier.REACTION_CXSMILES:
                reaction_smiles = ident.value

        # Extract conditions
        temperature_c = _extract_temperature(rxn.conditions)
        pressure_bar = _extract_pressure(rxn.conditions)
        atmosphere = _extract_atmosphere(rxn.conditions)
        time_seconds = _extract_time(rxn)

        # Extract yield from first outcome
        yield_pct, yield_type, selectivity = _extract_yields(rxn)

        # Extract provenance
        doi = rxn.provenance.doi if rxn.provenance.doi else None
        patent = rxn.provenance.patent if rxn.provenance.patent else None

        # Build reaction row
        reaction_row = {
            "reaction_id": reaction_id,
            "reaction_smiles": reaction_smiles,
            "temperature_c": temperature_c,
            "pressure_bar": pressure_bar,
            "time_seconds": int(time_seconds) if time_seconds is not None else None,
            "atmosphere": atmosphere,
            "yield_pct": yield_pct,
            "yield_type": yield_type,
            "selectivity": selectivity,
            "source": "ord",
            "source_id": reaction_id,
            "doi": doi,
            "patent_id": patent,
        }

        # Collect molecules and components from inputs
        mol_map: dict[str, dict] = {}  # inchikey → molecule row
        comp_list: list[dict] = []
        # Track (inchikey, role) to deduplicate components
        comp_seen: dict[tuple[str, str], int] = {}

        for _input_name, reaction_input in rxn.inputs.items():
            for compound in reaction_input.components:
                role = _ROLE_MAP.get(compound.reaction_role)
                if role is None or role == "product":
                    # Input compounds shouldn't be products; skip unknown roles
                    if compound.reaction_role not in (
                        reaction_pb2.ReactionRole.UNSPECIFIED,
                        reaction_pb2.ReactionRole.PRODUCT,
                        reaction_pb2.ReactionRole.BYPRODUCT,
                        reaction_pb2.ReactionRole.SIDE_PRODUCT,
                    ):
                        continue
                    if role is None:
                        continue

                parsed = _parse_compound(compound)
                if parsed is None:
                    continue

                inchikey, mol_row = parsed
                mol_map[inchikey] = mol_row

                mass_g, volume_ml, equivalents = _extract_amounts(compound)
                comp_key = (inchikey, role)
                if comp_key in comp_seen:
                    # Merge: sum mass and volume
                    idx = comp_seen[comp_key]
                    existing = comp_list[idx]
                    if mass_g is not None:
                        existing["mass_g"] = (existing["mass_g"] or 0) + mass_g
                    if volume_ml is not None:
                        existing["volume_ml"] = (existing["volume_ml"] or 0) + volume_ml
                else:
                    comp_row = {
                        "reaction_id": reaction_id,
                        "inchikey": inchikey,
                        "role": role,
                        "equivalents": equivalents,
                        "mass_g": mass_g,
                        "volume_ml": volume_ml,
                        "is_major": True,
                    }
                    comp_seen[comp_key] = len(comp_list)
                    comp_list.append(comp_row)

        # Collect products from outcomes
        for outcome in rxn.outcomes:
            for product in outcome.products:
                parsed = _parse_compound(product)
                if parsed is None:
                    continue
                inchikey, mol_row = parsed
                mol_map[inchikey] = mol_row

                product_yield = None
                for measurement in product.measurements:
                    if measurement.type == _YIELD_TYPE:
                        if measurement.percentage.value > 0:
                            product_yield = measurement.percentage.value

                is_desired = getattr(product, "is_desired_product", False)
                comp_key = (inchikey, "product")
                if comp_key not in comp_seen:
                    comp_row = {
                        "reaction_id": reaction_id,
                        "inchikey": inchikey,
                        "role": "product",
                        "is_major": bool(is_desired),
                        "yield_pct": product_yield,
                    }
                    comp_seen[comp_key] = len(comp_list)
                    comp_list.append(comp_row)

        if not mol_map:
            return None

        # Build conditions rows
        cond_list: list[dict] = []
        if temperature_c is not None:
            cond_list.append({
                "reaction_id": reaction_id,
                "condition_type": "temperature",
                "value": temperature_c,
                "unit": "celsius",
            })
        if pressure_bar is not None:
            cond_list.append({
                "reaction_id": reaction_id,
                "condition_type": "pressure",
                "value": pressure_bar,
                "unit": "bar",
            })
        if time_seconds is not None:
            cond_list.append({
                "reaction_id": reaction_id,
                "condition_type": "time",
                "value": float(time_seconds),
                "unit": "seconds",
            })

        return {
            "reaction": reaction_row,
            "molecules": list(mol_map.values()),
            "components": comp_list,
            "conditions": cond_list,
        }

    def load_batch(
        self, batch: list[dict], conn: Connection, load_id: uuid.UUID
    ) -> LoadStats:
        """Bulk insert a batch of transformed reactions."""
        stats = LoadStats()

        # 1. Collect all unique molecules across the batch
        all_molecules: dict[str, dict] = {}
        for record in batch:
            for mol_row in record["molecules"]:
                all_molecules[mol_row["inchikey"]] = mol_row

        # 2. Upsert molecules
        if all_molecules:
            stmt = pg_insert(molecules).values(list(all_molecules.values()))
            stmt = stmt.on_conflict_do_update(
                index_elements=["inchikey"],
                set_={
                    "sources": molecules.c.sources.op("||")(
                        stmt.excluded.sources
                    ),
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            conn.execute(stmt)

        # 3. Insert reactions
        reaction_rows = [record["reaction"] for record in batch]
        if reaction_rows:
            stmt = pg_insert(reactions).values(reaction_rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["reaction_id"])
            conn.execute(stmt)

        # 4. Insert reaction_components
        all_components: list[dict] = []
        for record in batch:
            all_components.extend(record["components"])
        if all_components:
            stmt = pg_insert(reaction_components).values(all_components)
            stmt = stmt.on_conflict_do_nothing(constraint="uq_rc_rxn_mol_role")
            conn.execute(stmt)

        # 5. Insert reaction_conditions
        all_conditions: list[dict] = []
        for record in batch:
            all_conditions.extend(record["conditions"])
        if all_conditions:
            stmt = pg_insert(reaction_conditions).values(all_conditions)
            stmt = stmt.on_conflict_do_nothing(constraint="uq_cond_rxn_type_phase")
            conn.execute(stmt)

        # 6. Upsert molecule_provenance
        prov_rows = [
            {"inchikey": ik, "source_name": "ord", "load_id": load_id}
            for ik in all_molecules
        ]
        if prov_rows:
            stmt = pg_insert(molecule_provenance).values(prov_rows)
            stmt = stmt.on_conflict_do_nothing()
            conn.execute(stmt)

        stats.loaded = len(batch)
        return stats


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_compound(
    compound: Any,
) -> tuple[str, dict] | None:
    """Extract SMILES from a compound, canonicalize, compute InChIKey + descriptors.

    Returns (inchikey, molecule_row_dict) or None if unparseable.
    """
    smiles = None
    inchi_str = None

    for ident in compound.identifiers:
        if ident.type == reaction_pb2.CompoundIdentifier.SMILES:
            smiles = ident.value
        elif ident.type == reaction_pb2.CompoundIdentifier.INCHI:
            inchi_str = ident.value

    # Try SMILES first, then InChI
    mol = None
    if smiles:
        mol = Chem.MolFromSmiles(smiles)
    if mol is None and inchi_str:
        mol = Chem.MolFromInchi(inchi_str)

    if mol is None:
        return None

    canonical_smiles = Chem.MolToSmiles(mol)
    if not inchi_str:
        inchi_str = rdinchi.MolToInchi(mol)
    if inchi_str is None:
        return None

    inchikey = rdinchi.InchiToInchiKey(inchi_str)
    if inchikey is None:
        return None

    mol_row = {
        "inchikey": inchikey,
        "canonical_smiles": canonical_smiles,
        "inchi": inchi_str,
        "mol_formula": rdMolDescriptors.CalcMolFormula(mol),
        "mol_weight": Descriptors.MolWt(mol),
        "exact_mass": Descriptors.ExactMolWt(mol),
        "logp": Crippen.MolLogP(mol),
        "tpsa": Descriptors.TPSA(mol),
        "hba": rdMolDescriptors.CalcNumHBA(mol),
        "hbd": rdMolDescriptors.CalcNumHBD(mol),
        "num_rotatable": rdMolDescriptors.CalcNumRotatableBonds(mol),
        "num_rings": rdMolDescriptors.CalcNumRings(mol),
        "sources": ["ord"],
    }
    return inchikey, mol_row


def _extract_temperature(
    conditions: reaction_pb2.ReactionConditions,
) -> float | None:
    """Extract temperature in Celsius from reaction conditions."""
    if not conditions.HasField("temperature"):
        return None
    temp = conditions.temperature
    if not temp.HasField("setpoint"):
        return None
    setpoint = temp.setpoint
    if setpoint.value == 0 and setpoint.units == 0:
        return None
    converter = _TEMP_UNITS.get(setpoint.units)
    if converter is None:
        return None
    return round(converter(setpoint.value), 2)


def _extract_pressure(
    conditions: reaction_pb2.ReactionConditions,
) -> float | None:
    """Extract pressure in bar from reaction conditions."""
    if not conditions.HasField("pressure"):
        return None
    pressure = conditions.pressure
    if not pressure.HasField("setpoint"):
        return None
    setpoint = pressure.setpoint
    if setpoint.value == 0 and setpoint.units == 0:
        return None
    converter = _PRESSURE_UNITS.get(setpoint.units)
    if converter is None:
        return None
    return round(converter(setpoint.value), 4)


def _extract_atmosphere(
    conditions: reaction_pb2.ReactionConditions,
) -> str | None:
    """Extract atmosphere type from reaction conditions."""
    if not conditions.HasField("pressure"):
        return None
    pressure = conditions.pressure
    if not pressure.HasField("atmosphere"):
        return None
    return _ATMOSPHERE_MAP.get(pressure.atmosphere.type)


def _extract_time(rxn: reaction_pb2.Reaction) -> float | None:
    """Extract reaction time in seconds from outcomes or conditions."""
    # Try outcomes first (reaction_time on the outcome)
    for outcome in rxn.outcomes:
        if outcome.HasField("reaction_time"):
            rt = outcome.reaction_time
            if rt.value > 0:
                converter = _TIME_UNITS.get(rt.units)
                if converter:
                    return round(converter(rt.value), 1)

    # Fallback: conditions.stirring duration or other time fields
    return None


def _extract_yields(
    rxn: reaction_pb2.Reaction,
) -> tuple[float | None, str | None, str | None]:
    """Extract best yield and selectivity from reaction outcomes.

    Returns (yield_pct, yield_type, selectivity).
    """
    best_yield = None
    yield_type = None
    selectivity = None

    for outcome in rxn.outcomes:
        for product in outcome.products:
            for measurement in product.measurements:
                if measurement.type == _YIELD_TYPE:
                    pct = measurement.percentage.value
                    if pct > 0 and (best_yield is None or pct > best_yield):
                        best_yield = round(pct, 2)
                        yield_type = "percentage"
                elif measurement.type == _SELECTIVITY_TYPE:
                    if measurement.percentage.value > 0:
                        selectivity = f"{measurement.percentage.value:.1f}%"

    return best_yield, yield_type, selectivity


def _extract_amounts(
    compound: Any,
) -> tuple[float | None, float | None, float | None]:
    """Extract mass (g), volume (mL), and equivalents from a compound.

    Returns (mass_g, volume_ml, equivalents).
    """
    mass_g = None
    volume_ml = None
    equivalents = None

    if not compound.HasField("amount"):
        return mass_g, volume_ml, equivalents

    amount = compound.amount

    if amount.HasField("mass"):
        converter = _MASS_UNITS.get(amount.mass.units)
        if converter and amount.mass.value > 0:
            mass_g = round(converter(amount.mass.value), 6)

    if amount.HasField("volume"):
        converter = _VOLUME_UNITS.get(amount.volume.units)
        if converter and amount.volume.value > 0:
            volume_ml = round(converter(amount.volume.value), 6)

    if amount.HasField("moles"):
        # Store moles as equivalents (relative to limiting reagent)
        # ORD doesn't directly give equivalents, but moles can be used
        pass

    return mass_g, volume_ml, equivalents
