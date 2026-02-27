"""ChemWorldModel CLI — data loading, schema management, and query tools."""

from __future__ import annotations

from pathlib import Path

import click


@click.group()
def cli() -> None:
    """ChemWorldModel — an open knowledge graph for chemistry."""


@cli.command()
def init() -> None:
    """Bootstrap the database schema via Alembic migrations."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    click.echo("Database schema is up to date.")


# ---------------------------------------------------------------------------
# load command group
# ---------------------------------------------------------------------------


@cli.command()
def stats() -> None:
    """Print database statistics (molecule, reaction, edge counts)."""
    from sqlalchemy import text

    from chemworldmodel.db.engine import get_sync_engine

    engine = get_sync_engine()
    with engine.connect() as conn:
        mol_count = conn.execute(text("SELECT COUNT(*) FROM chem.molecules")).scalar()
        rxn_count = conn.execute(text("SELECT COUNT(*) FROM rxn.reactions")).scalar()
        comp_count = conn.execute(
            text("SELECT COUNT(*) FROM rxn.reaction_components")
        ).scalar()
        bio_count = conn.execute(
            text("SELECT COUNT(*) FROM chem.bioactivities")
        ).scalar()
        hazard_count = conn.execute(
            text("SELECT COUNT(*) FROM onto.hazard_data")
        ).scalar()

    click.echo(f"Molecules:            {mol_count:>12,}")
    click.echo(f"Reactions:            {rxn_count:>12,}")
    click.echo(f"Reaction components:  {comp_count:>12,}")
    click.echo(f"Bioactivities:        {bio_count:>12,}")
    click.echo(f"Hazard records:       {hazard_count:>12,}")


@cli.group()
def load() -> None:
    """Data loading commands."""


@load.command()
@click.option(
    "--data-dir",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to ORD data directory containing .pb.gz files.",
)
@click.option("--batch-size", default=5000, type=int, show_default=True)
@click.option(
    "--limit",
    default=None,
    type=int,
    help="Max reactions to load (for testing).",
)
@click.option(
    "--skip-fingerprints",
    is_flag=True,
    help="Skip post-load fingerprint computation.",
)
def ord(data_dir: Path, batch_size: int, limit: int | None, skip_fingerprints: bool) -> None:
    """Load ORD reaction data from protobuf files."""
    from chemworldmodel.db.engine import get_sync_engine
    from chemworldmodel.loaders.fingerprints import backfill_all
    from chemworldmodel.loaders.ord_loader import ORDLoader

    engine = get_sync_engine()
    loader = ORDLoader(engine=engine, batch_size=batch_size)

    click.echo(f"Loading ORD data from {data_dir} (batch_size={batch_size}) ...")
    load_id = loader.run(data_dir=data_dir, limit=limit)
    click.echo(f"Load complete. load_id={load_id}")

    if not skip_fingerprints:
        click.echo("Computing mol column and fingerprints via RDKit cartridge ...")
        backfill_all(engine)
        click.echo("Fingerprints complete.")


@load.command()
@click.option("--batch-size", default=50000, type=int, show_default=True)
def fingerprints(batch_size: int) -> None:
    """Compute mol column and Morgan fingerprints for molecules missing them."""
    from chemworldmodel.db.engine import get_sync_engine
    from chemworldmodel.loaders.fingerprints import backfill_all

    engine = get_sync_engine()
    click.echo("Computing mol column and fingerprints ...")
    backfill_all(engine, batch_size)
    click.echo("Done.")


@load.command(name="graph")
@click.option("--batch-size", default=5000, type=int, show_default=True)
@click.option("--rebuild", is_flag=True, help="Clear existing graph before rebuilding.")
def graph_cmd(batch_size: int, rebuild: bool) -> None:
    """Build AGE graph from relational data (molecules, reactions, edges)."""
    from chemworldmodel.db.engine import get_sync_engine
    from chemworldmodel.graph.builder import build_graph

    engine = get_sync_engine()
    click.echo(f"Building AGE graph (batch_size={batch_size}, rebuild={rebuild}) ...")
    stats = build_graph(engine, batch_size=batch_size, rebuild=rebuild)
    click.echo(
        f"Graph complete: {stats['molecules']} molecules, "
        f"{stats['reactions']} reactions, "
        f"edges: {stats['edges']}"
    )


@load.command(name="materialise")
@click.option("--similar-threshold", default=0.85, type=click.FloatRange(0.0, 1.0), show_default=True)
@click.option("--precursor-depth", default=4, type=click.IntRange(1, 4), show_default=True)
@click.option("--batch-size", default=5000, type=int, show_default=True)
@click.option("--skip-similar", is_flag=True, help="Skip SIMILAR_TO edge creation.")
@click.option("--skip-precursor", is_flag=True, help="Skip PRECURSOR_OF edge creation.")
@click.option("--skip-hazard", is_flag=True, help="Skip HAS_HAZARD property update.")
def materialise_cmd(
    similar_threshold: float,
    precursor_depth: int,
    batch_size: int,
    skip_similar: bool,
    skip_precursor: bool,
    skip_hazard: bool,
) -> None:
    """Materialise SIMILAR_TO, PRECURSOR_OF edges and HAS_HAZARD properties in the AGE graph."""
    from chemworldmodel.db.engine import get_sync_engine
    from chemworldmodel.graph.materialise import (
        materialise_has_hazard,
        materialise_precursor_of,
        materialise_similar_to,
    )

    engine = get_sync_engine()

    if not skip_similar:
        click.echo(f"Materialising SIMILAR_TO edges (threshold={similar_threshold}) ...")
        similar_count = materialise_similar_to(
            engine, threshold=similar_threshold, batch_size=batch_size
        )
        click.echo(f"Created {similar_count} SIMILAR_TO edges.")

    if not skip_precursor:
        click.echo(f"Materialising PRECURSOR_OF edges (max_depth={precursor_depth}) ...")
        precursor_count = materialise_precursor_of(
            engine, max_depth=precursor_depth, batch_size=batch_size
        )
        click.echo(f"Created {precursor_count} PRECURSOR_OF edges.")

    if not skip_hazard:
        click.echo("Updating Molecule nodes with GHS hazard properties ...")
        hazard_count = materialise_has_hazard(engine, batch_size=batch_size)
        click.echo(f"Updated {hazard_count} molecules with hazard data.")


@load.command()
@click.option("--batch-size", default=5000, type=int, show_default=True)
@click.option("--api-batch-size", default=100, type=int, show_default=True,
              help="InChIKeys per PubChem API request.")
@click.option("--limit", default=None, type=int, help="Max molecules to enrich.")
def pubchem(batch_size: int, api_batch_size: int, limit: int | None) -> None:
    """Enrich molecules with PubChem properties (CID, IUPAC name, XLogP)."""
    from chemworldmodel.db.engine import get_sync_engine
    from chemworldmodel.loaders.pubchem_loader import PubChemLoader

    engine = get_sync_engine()
    loader = PubChemLoader(engine=engine, batch_size=batch_size)

    click.echo("Enriching molecules from PubChem ...")
    load_id = loader.run(limit=limit, api_batch_size=api_batch_size)
    click.echo(f"PubChem enrichment complete. load_id={load_id}")


@load.command()
@click.option("--obo-path", type=click.Path(exists=True, path_type=Path),
              default=None, help="Path to chebi.obo file (downloads if omitted).")
@click.option("--batch-size", default=5000, type=int, show_default=True)
@click.option("--limit", default=None, type=int, help="Max terms to load.")
def chebi(obo_path: Path | None, batch_size: int, limit: int | None) -> None:
    """Load ChEBI ontology (molecule roles and classifications)."""
    from chemworldmodel.db.engine import get_sync_engine
    from chemworldmodel.loaders.chebi_loader import ChEBILoader

    engine = get_sync_engine()
    loader = ChEBILoader(engine=engine, batch_size=batch_size)

    click.echo("Loading ChEBI ontology ...")
    load_id = loader.run(obo_path=obo_path, limit=limit)
    click.echo(f"ChEBI load complete. load_id={load_id}")


@load.command()
@click.option("--ghs-file", type=click.Path(exists=True, path_type=Path),
              default=None, help="Path to GHS JSON lines file (uses API if omitted).")
@click.option("--batch-size", default=1000, type=int, show_default=True)
@click.option("--limit", default=None, type=int, help="Max molecules to process.")
def ghs(ghs_file: Path | None, batch_size: int, limit: int | None) -> None:
    """Load GHS hazard classifications from PubChem."""
    from chemworldmodel.db.engine import get_sync_engine
    from chemworldmodel.loaders.ghs_loader import GHSLoader

    engine = get_sync_engine()
    loader = GHSLoader(engine=engine, batch_size=batch_size)

    click.echo("Loading GHS hazard data ...")
    load_id = loader.run(ghs_file=ghs_file, limit=limit)
    click.echo(f"GHS load complete. load_id={load_id}")


@load.command()
@click.option("--db-path", type=click.Path(exists=True, path_type=Path),
              required=True, help="Path to ChEMBL SQLite database file.")
@click.option("--batch-size", default=5000, type=int, show_default=True)
@click.option("--limit", default=None, type=int, help="Max activity records to load.")
def chembl(db_path: Path, batch_size: int, limit: int | None) -> None:
    """Load bioactivity data from ChEMBL SQLite dump."""
    from chemworldmodel.db.engine import get_sync_engine
    from chemworldmodel.loaders.chembl_loader import ChEMBLLoader

    engine = get_sync_engine()
    loader = ChEMBLLoader(engine=engine, batch_size=batch_size)

    click.echo(f"Loading ChEMBL bioactivities from {db_path} ...")
    load_id = loader.run(db_path=db_path, limit=limit)
    click.echo(f"ChEMBL load complete. load_id={load_id}")


@load.command()
@click.option("--batch-size", default=10000, type=int, show_default=True)
def classify(batch_size: int) -> None:
    """Classify reactions by SMARTS pattern matching."""
    from chemworldmodel.db.engine import get_sync_engine
    from chemworldmodel.loaders.classify import classify_batch

    engine = get_sync_engine()
    click.echo("Classifying reactions ...")
    total = classify_batch(engine, batch_size)
    click.echo(f"Classified {total} reactions.")


# ---------------------------------------------------------------------------
# query command
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("question")
def query(question: str) -> None:
    """Ask a chemistry question in natural language."""
    from chemworldmodel.config import get_settings
    from chemworldmodel.db.engine import get_sync_engine
    from chemworldmodel.query.nl_to_sql import NLToSQL

    settings = get_settings()
    engine = get_sync_engine()
    pipeline = NLToSQL(engine=engine, settings=settings)

    click.echo(f"Query: {question}\n")
    try:
        result = pipeline.query_sync(question)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    click.echo(f"Answer:\n{result.answer}\n")
    click.echo(f"Reactions found: {result.reaction_count}")
    if result.citations:
        shown = result.citations[:10]
        click.echo(f"Citations: {', '.join(shown)}")
        if result.reaction_count > 10:
            click.echo(f"  ... and {result.reaction_count - 10} more")
    click.echo(f"\nSQL:\n{result.sql}")
