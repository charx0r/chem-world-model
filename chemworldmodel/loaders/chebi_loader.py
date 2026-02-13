"""ChEBI ontology loader (WP5.2).

Downloads the ChEBI OBO file, parses the ontology with pronto,
populates onto.molecule_roles with the is_a hierarchy, and links
ChEBI entries to chem.molecules via InChIKey (computed from InChI).
"""

from __future__ import annotations

import gzip
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterator

import httpx
import structlog
from sqlalchemy import Connection, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from chemworldmodel.db.schema import molecule_provenance, molecule_roles
from chemworldmodel.loaders.base import BaseLoader, LoadStats

log = structlog.get_logger()

# ChEBI OBO download URL
CHEBI_OBO_URL = "https://ftp.ebi.ac.uk/pub/databases/chebi/ontology/chebi.obo.gz"


def _inchikey_from_term(term: Any) -> str | None:
    """Extract InChIKey from a ChEBI pronto term.

    ChEBI OBO stores InChI (not InChIKey) in xrefs. We find the InChI
    string and compute InChIKey via RDKit.
    """
    inchi_str = None

    # Check xrefs for InChI
    for xref in term.xrefs:
        xref_id = str(xref.id) if hasattr(xref, "id") else str(xref)
        if xref_id.startswith("InChI="):
            inchi_str = xref_id
            break

    if not inchi_str:
        return None

    try:
        from rdkit import Chem
        from rdkit.Chem import inchi as rdinchi

        mol = rdinchi.MolFromInchi(inchi_str)
        if mol is None:
            return None
        return rdinchi.InchiToInchiKey(inchi_str)
    except Exception:
        return None


class ChEBILoader(BaseLoader):
    """Load ChEBI ontology for molecular role classification."""

    source_name = "chebi"

    def extract(self, **kwargs: Any) -> Iterator[Any]:
        """Parse ChEBI OBO file and yield ontology terms.

        If obo_path is provided, reads from that file. Otherwise downloads
        from EBI FTP.
        """
        import pronto

        obo_path: Path | None = kwargs.get("obo_path")

        if obo_path is None:
            obo_path = self._download_obo()

        self.log.info("parsing_chebi_obo", path=str(obo_path))
        onto = pronto.Ontology(str(obo_path))

        limit: int | None = kwargs.get("limit")
        count = 0

        for term in onto.terms():
            yield term
            count += 1
            if limit and count >= limit:
                return

    def transform_one(self, raw_item: Any) -> dict | None:
        """Transform a pronto Term into a role dict + optional molecule link."""
        term = raw_item

        chebi_id = term.id
        if not chebi_id.startswith("CHEBI:"):
            return None

        name = term.name
        if not name:
            return None

        # Get immediate parent (first is_a)
        parent_id = None
        for parent in term.superclasses(distance=1, with_self=False):
            if parent.id.startswith("CHEBI:"):
                parent_id = parent.id
                break

        description = None
        if term.definition:
            # OBO definitions are quoted: "actual definition"
            defn = str(term.definition)
            if defn.startswith('"') and defn.endswith('"'):
                defn = defn[1:-1]
            description = defn

        # Compute InChIKey from InChI if available
        inchikey = _inchikey_from_term(term)

        return {
            "role_id": chebi_id,
            "parent_id": parent_id,
            "name": name,
            "description": description,
            "inchikey": inchikey,
        }

    def load_batch(
        self, batch: list[dict], conn: Connection, load_id: uuid.UUID
    ) -> LoadStats:
        """Insert roles into onto.molecule_roles and link to molecules.

        Uses two passes to handle self-referencing FK on parent_id:
        1. Insert all roles with parent_id=NULL
        2. Update parent_id for all roles
        """
        stats = LoadStats()

        role_rows = []
        mol_links = []

        for record in batch:
            role_rows.append({
                "role_id": record["role_id"],
                "parent_id": record["parent_id"],
                "name": record["name"],
                "description": record["description"],
            })

            if record.get("inchikey"):
                mol_links.append({
                    "inchikey": record["inchikey"],
                    "chebi_id": record["role_id"],
                })

        # Pass 1: upsert roles WITHOUT parent_id (avoids FK violations)
        for row in role_rows:
            try:
                conn.execute(
                    pg_insert(molecule_roles)
                    .values(
                        role_id=row["role_id"],
                        name=row["name"],
                        description=row["description"],
                    )
                    .on_conflict_do_update(
                        index_elements=["role_id"],
                        set_={
                            "name": row["name"],
                            "description": row["description"],
                        },
                    )
                )
                stats.loaded += 1
            except Exception as e:
                stats.add_error(str(e), row["role_id"])

        # Pass 2: update parent_id (parent now guaranteed to exist
        # if it was in this or a previous batch). Use savepoints so a
        # failed FK update doesn't abort the entire transaction.
        for row in role_rows:
            if row["parent_id"] is None:
                continue
            try:
                nested = conn.begin_nested()
                conn.execute(
                    text(
                        "UPDATE onto.molecule_roles "
                        "SET parent_id = :parent_id "
                        "WHERE role_id = :role_id"
                    ),
                    {"role_id": row["role_id"], "parent_id": row["parent_id"]},
                )
                nested.commit()
            except Exception:
                nested.rollback()

        # Link ChEBI → molecules (update chebi_id + provenance)
        for link in mol_links:
            try:
                result = conn.execute(
                    text(
                        "UPDATE chem.molecules SET chebi_id = :chebi_id, "
                        "updated_at = NOW() "
                        "WHERE inchikey = :inchikey AND chebi_id IS NULL"
                    ),
                    link,
                )
                if result.rowcount > 0:
                    conn.execute(
                        pg_insert(molecule_provenance)
                        .values(
                            inchikey=link["inchikey"],
                            source_name="chebi",
                            source_id=link["chebi_id"],
                            load_id=load_id,
                        )
                        .on_conflict_do_update(
                            index_elements=["inchikey", "source_name"],
                            set_={
                                "source_id": link["chebi_id"],
                                "load_id": load_id,
                            },
                        )
                    )
            except Exception as e:
                stats.add_error(str(e), link["inchikey"])

        return stats

    def _download_obo(self) -> Path:
        """Download ChEBI OBO file to a temp directory."""
        self.log.info("downloading_chebi_obo", url=CHEBI_OBO_URL)
        tmp = Path(tempfile.mkdtemp()) / "chebi.obo"

        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.get(CHEBI_OBO_URL)
            resp.raise_for_status()

            decompressed = gzip.decompress(resp.content)
            tmp.write_bytes(decompressed)

        self.log.info("chebi_obo_downloaded", path=str(tmp), size=tmp.stat().st_size)
        return tmp
