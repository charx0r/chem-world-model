"""Add chem.bioactivities table and iupac_name column to molecules.

Revision ID: 002
Revises: 001
Create Date: 2026-03-28

Supports WP5 data enrichment: ChEMBL bioactivity data and PubChem
compound enrichment (IUPAC name, complexity).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # chem.molecules — add columns for PubChem enrichment
    # ------------------------------------------------------------------
    op.add_column(
        "molecules",
        sa.Column("iupac_name", sa.Text),
        schema="chem",
    )
    op.add_column(
        "molecules",
        sa.Column("complexity", sa.Float),
        schema="chem",
    )

    # ------------------------------------------------------------------
    # chem.bioactivities — ChEMBL bioactivity data
    # ------------------------------------------------------------------
    op.create_table(
        "bioactivities",
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
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "inchikey",
            "target_chembl_id",
            "activity_type",
            "assay_chembl_id",
            name="uq_bioact_mol_target_type_assay",
        ),
        schema="chem",
    )

    # Indexes for bioactivities
    op.create_index(
        "idx_bioact_inchikey",
        "bioactivities",
        ["inchikey"],
        schema="chem",
    )
    op.create_index(
        "idx_bioact_target",
        "bioactivities",
        ["target_chembl_id"],
        schema="chem",
    )
    op.create_index(
        "idx_bioact_type",
        "bioactivities",
        ["activity_type"],
        schema="chem",
    )


def downgrade() -> None:
    op.drop_table("bioactivities", schema="chem")
    op.drop_column("molecules", "complexity", schema="chem")
    op.drop_column("molecules", "iupac_name", schema="chem")
