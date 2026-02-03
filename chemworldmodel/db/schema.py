"""Core relational schema for ChemWorldModel.

Defines all tables across 5 schemas (chem, rxn, onto, ingest, lineage)
using SQLAlchemy Core. The MetaData object is imported by Alembic for
migration generation.
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.types import UserDefinedType


# ---------------------------------------------------------------------------
# Custom PostgreSQL types for chemistry extensions
# ---------------------------------------------------------------------------


class RDKitMol(UserDefinedType):
    """RDKit cartridge 'mol' type — enables substructure search via GiST."""

    cache_ok = True

    def get_col_spec(self) -> str:
        return "mol"


class PgBit(UserDefinedType):
    """PostgreSQL fixed-length bit string — used for Morgan fingerprints."""

    cache_ok = True

    def __init__(self, length: int = 2048):
        self.length = length

    def get_col_spec(self) -> str:
        return f"bit({self.length})"


# ---------------------------------------------------------------------------
# Shared metadata instance (imported by Alembic env.py)
# ---------------------------------------------------------------------------

metadata = sa.MetaData()

# ---------------------------------------------------------------------------
# chem schema
# ---------------------------------------------------------------------------

molecules = sa.Table(
    "molecules",
    metadata,
    sa.Column("inchikey", sa.Text, primary_key=True),
    sa.Column("canonical_smiles", sa.Text, nullable=False),
    sa.Column("inchi", sa.Text),
    sa.Column("mol_formula", sa.Text),
    sa.Column("mol_weight", sa.Float),
    sa.Column("exact_mass", sa.Float),
    sa.Column("logp", sa.Float),
    sa.Column("tpsa", sa.Float),
    sa.Column("hba", sa.Integer),
    sa.Column("hbd", sa.Integer),
    sa.Column("num_rotatable", sa.Integer),
    sa.Column("num_rings", sa.Integer),
    sa.Column("mol", RDKitMol()),
    sa.Column("fp_morgan", PgBit(2048)),
    sa.Column("fp_morgan_vec", Vector(2048)),
    sa.Column("iupac_name", sa.Text),
    sa.Column("complexity", sa.Float),
    sa.Column("sources", sa.ARRAY(sa.Text), server_default="{}"),
    sa.Column("cas_number", sa.Text),
    sa.Column("chembl_id", sa.Text),
    sa.Column("pubchem_cid", sa.BigInteger),
    sa.Column("chebi_id", sa.Text),
    sa.Column("commercially_available", sa.Boolean),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    schema="chem",
)

# ---------------------------------------------------------------------------
# rxn schema
# ---------------------------------------------------------------------------

reactions = sa.Table(
    "reactions",
    metadata,
    sa.Column("reaction_id", sa.Text, primary_key=True),
    sa.Column("reaction_smiles", sa.Text),
    sa.Column("reaction_class", sa.Text),
    sa.Column("rxno_id", sa.Text),
    sa.Column("temperature_c", sa.Float),
    sa.Column("pressure_bar", sa.Float),
    sa.Column("time_seconds", sa.Integer),
    sa.Column("atmosphere", sa.Text),
    sa.Column("yield_pct", sa.Float),
    sa.Column("yield_type", sa.Text),
    sa.Column("selectivity", sa.Text),
    sa.Column("procedure_text", sa.Text),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("source_id", sa.Text),
    sa.Column("source_version", sa.Text),
    sa.Column("patent_id", sa.Text),
    sa.Column("doi", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    schema="rxn",
)

reaction_components = sa.Table(
    "reaction_components",
    metadata,
    sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
    sa.Column(
        "reaction_id",
        sa.Text,
        sa.ForeignKey("rxn.reactions.reaction_id"),
        nullable=False,
    ),
    sa.Column(
        "inchikey",
        sa.Text,
        sa.ForeignKey("chem.molecules.inchikey"),
        nullable=False,
    ),
    sa.Column(
        "role",
        sa.Text,
        nullable=False,
    ),
    sa.Column("stoichiometry", sa.Float),
    sa.Column("equivalents", sa.Float),
    sa.Column("mass_g", sa.Float),
    sa.Column("volume_ml", sa.Float),
    sa.Column("is_major", sa.Boolean, server_default=sa.text("TRUE")),
    sa.Column("yield_pct", sa.Float),
    sa.CheckConstraint(
        "role IN ('reactant','product','catalyst','solvent',"
        "'reagent','base','acid','ligand','additive','internal_standard')",
        name="ck_rc_role",
    ),
    sa.UniqueConstraint("reaction_id", "inchikey", "role", name="uq_rc_rxn_mol_role"),
    schema="rxn",
)

reaction_conditions = sa.Table(
    "reaction_conditions",
    metadata,
    sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
    sa.Column(
        "reaction_id",
        sa.Text,
        sa.ForeignKey("rxn.reactions.reaction_id"),
        nullable=False,
    ),
    sa.Column("condition_type", sa.Text, nullable=False),
    sa.Column("value", sa.Float),
    sa.Column("unit", sa.Text, nullable=False),
    sa.Column("precision", sa.Float),
    sa.Column("phase", sa.Text),
    sa.UniqueConstraint(
        "reaction_id", "condition_type", "phase", name="uq_cond_rxn_type_phase"
    ),
    schema="rxn",
)

bioactivities = sa.Table(
    "bioactivities",
    metadata,
    sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
    sa.Column(
        "inchikey",
        sa.Text,
        sa.ForeignKey("chem.molecules.inchikey"),
        nullable=False,
    ),
    sa.Column("target_chembl_id", sa.Text, nullable=False),
    sa.Column("target_name", sa.Text),
    sa.Column("target_organism", sa.Text),
    sa.Column("activity_type", sa.Text, nullable=False),
    sa.Column("value", sa.Float),
    sa.Column("unit", sa.Text),
    sa.Column("relation", sa.Text),
    sa.Column("assay_chembl_id", sa.Text, nullable=False),
    sa.Column("source_chembl_id", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    sa.UniqueConstraint(
        "inchikey",
        "target_chembl_id",
        "activity_type",
        "assay_chembl_id",
        name="uq_bioact_mol_target_type_assay",
    ),
    schema="chem",
)

# ---------------------------------------------------------------------------
# lineage schema
# ---------------------------------------------------------------------------

data_loads = sa.Table(
    "data_loads",
    metadata,
    sa.Column(
        "load_id",
        sa.Uuid,
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    ),
    sa.Column("source_name", sa.Text, nullable=False),
    sa.Column("source_version", sa.Text),
    sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
    sa.Column(
        "status",
        sa.Text,
        server_default="running",
    ),
    sa.Column("records_loaded", sa.Integer, server_default="0"),
    sa.Column("records_skipped", sa.Integer, server_default="0"),
    sa.Column("records_failed", sa.Integer, server_default="0"),
    sa.Column("error_log", sa.JSON),
    sa.Column("loader_version", sa.Text),
    sa.Column("config", sa.JSON),
    sa.CheckConstraint(
        "status IN ('running','completed','failed')",
        name="ck_dl_status",
    ),
    schema="lineage",
)

molecule_provenance = sa.Table(
    "molecule_provenance",
    metadata,
    sa.Column(
        "inchikey",
        sa.Text,
        sa.ForeignKey("chem.molecules.inchikey"),
        nullable=False,
    ),
    sa.Column("source_name", sa.Text, nullable=False),
    sa.Column("source_id", sa.Text),
    sa.Column(
        "load_id",
        sa.Uuid,
        sa.ForeignKey("lineage.data_loads.load_id"),
    ),
    sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    sa.PrimaryKeyConstraint("inchikey", "source_name"),
    schema="lineage",
)

# ---------------------------------------------------------------------------
# onto schema
# ---------------------------------------------------------------------------

reaction_classes = sa.Table(
    "reaction_classes",
    metadata,
    sa.Column("class_id", sa.Text, primary_key=True),
    sa.Column(
        "parent_id",
        sa.Text,
        sa.ForeignKey("onto.reaction_classes.class_id"),
    ),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("rxno_id", sa.Text),
    sa.Column("description", sa.Text),
    sa.Column("smarts_pattern", sa.Text),
    sa.Column("level", sa.Integer, nullable=False, server_default="0"),
    schema="onto",
)

molecule_roles = sa.Table(
    "molecule_roles",
    metadata,
    sa.Column("role_id", sa.Text, primary_key=True),
    sa.Column(
        "parent_id",
        sa.Text,
        sa.ForeignKey("onto.molecule_roles.role_id"),
    ),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("description", sa.Text),
    schema="onto",
)

hazard_data = sa.Table(
    "hazard_data",
    metadata,
    sa.Column(
        "inchikey",
        sa.Text,
        sa.ForeignKey("chem.molecules.inchikey"),
        nullable=False,
    ),
    sa.Column("ghs_codes", sa.ARRAY(sa.Text)),
    sa.Column("signal_word", sa.Text),
    sa.Column("pictograms", sa.ARRAY(sa.Text)),
    sa.Column("source", sa.Text, server_default="pubchem_ghs"),
    sa.PrimaryKeyConstraint("inchikey", "source"),
    schema="onto",
)
