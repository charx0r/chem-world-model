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
