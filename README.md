# ChemWorldModel

<p align="center">
  <img src="web/public/logo.svg" width="80" alt="ChemWorldModel">
</p>

A queryable knowledge graph of chemical reactions built on PostgreSQL 17. Ingests ~1.8 million reactions from the Open Reaction Database, enriches molecules from PubChem/ChEBI/ChEMBL/GHS, and exposes the data through a natural language query interface, molecular similarity search, and retrosynthetic route planning.

## Data Sources

| Source | Records | Format | What it provides |
|--------|---------|--------|-----------------|
| [Open Reaction Database](https://github.com/open-reaction-database/ord-data) | ~1.8M reactions | `.pb.gz` protobuf | Reactions, components, conditions, yields, procedure text. Primary data source. |
| [PubChem](https://pubchem.ncbi.nlm.nih.gov/) | Enrichment | REST API (PUG) | IUPAC names, CIDs, exact mass, XLogP, complexity scores. Also GHS hazard classifications. |
| [ChEBI](https://www.ebi.ac.uk/chebi/) | Enrichment | OBO ontology | Chemical ontology IDs, role classifications, InChI cross-references. |
| [ChEMBL](https://www.ebi.ac.uk/chembl/) | Enrichment | SQLite dump | Bioactivity data — IC50, Ki, EC50 values against biological targets (HERG, COX-2, etc.). |

The ORD dataset is downloaded via Git LFS (~3-5 GB). Enrichment loaders pull from public APIs or local database dumps and match to existing molecules by InChIKey.

## Stack

- **Database:** PostgreSQL 17 with four compiled-from-source extensions (RDKit cartridge, Apache AGE, pgvector, TimescaleDB)
- **Backend:** Python 3.12 — FastAPI, SQLAlchemy Core, Click CLI, RDKit, ord-schema
- **Frontend:** Next.js 16, React 19, Tailwind CSS 4, RDKit.js (WASM), Cytoscape.js
- **Infra:** Docker Compose, multi-stage Dockerfile for the custom PG image, uv for Python packaging

## Data Architecture

### Storage Layout

Five PostgreSQL schemas separate concerns:

```
chem        molecules, bioactivities
rxn         reactions, reaction_components, reaction_conditions
onto        reaction_classes, molecule_roles, hazard_data
lineage     data_loads, molecule_provenance
ingest      staging (reserved for future use)
```

On top of the relational layer sits an Apache AGE property graph (`chemworld`) that mirrors the reaction network as a directed graph. The relational schema is the source of truth; the graph is derived and rebuilt from it.

### Molecule Table (`chem.molecules`)

The primary key is `inchikey` (the IUPAC InChIKey), not SMILES. InChIKey is globally unique and canonical — the same molecule always produces the same key regardless of how the SMILES was drawn.

Each molecule row stores:

- **Structural:** `canonical_smiles` (RDKit-canonicalised), `inchi`, `mol` (RDKit cartridge type for substructure search)
- **Fingerprints:** `fp_morgan` as `bit(2048)` (Morgan/ECFP4, radius 2) for Tanimoto via pgvector's Jaccard distance, plus `fp_morgan_vec` as a float vector for HNSW indexing
- **Descriptors:** molecular weight, exact mass, LogP, TPSA, HBA/HBD counts, rotatable bonds, ring count, complexity
- **External IDs:** PubChem CID, ChEMBL ID, ChEBI ID, CAS number
- **Metadata:** `sources` array tracking which loaders touched the row, `commercially_available` flag, timestamps

### Reaction Tables (`rxn.*`)

`rxn.reactions` holds one row per experimentally observed reaction with conditions (temperature in Celsius, pressure in bar, time in seconds, atmosphere) and yield data.

`rxn.reaction_components` is the central join table. It links molecules to reactions with a `role` column constrained to: reactant, product, catalyst, solvent, reagent, base, acid, ligand, additive, internal_standard. The unique constraint on `(reaction_id, inchikey, role)` prevents duplicate entries.

`rxn.reaction_conditions` stores normalised condition measurements per reaction, typed by `condition_type` (temperature, pressure, time, stirring, pH) and tagged with `phase` (initial, during, final).

### Graph Layer (Apache AGE)

The `chemworld` graph has two node types and six edge types:

```
(:Molecule) —[:REACTANT_IN]—> (:Reaction)
(:Reaction) —[:PRODUCT_OF]—>  (:Molecule)
(:Molecule) —[:CATALYSES]—>   (:Reaction)
(:Molecule) —[:SOLVENT_IN]—>  (:Reaction)
(:Molecule) —[:SIMILAR_TO]—   (:Molecule)     # materialised from pgvector KNN
(:Molecule) —[:PRECURSOR_OF]—>(:Molecule)     # materialised shortcut edges
```

The first four edge types are built directly from `rxn.reaction_components`. The last two are materialised in a separate step:

- `SIMILAR_TO` edges are created by running pgvector KNN on Morgan fingerprints with a Tanimoto threshold (default 0.85). One directed edge per pair (lexicographic ordering on InChIKey).
- `PRECURSOR_OF` edges are shortcut edges for multi-step synthesis paths (up to 4 steps). They store `step_count` and `cumulative_yield` so route queries don't have to traverse the full path every time.

### Provenance Tracking (`lineage.*`)

Every data load creates a row in `lineage.data_loads` with a UUID, source name, version, start/end timestamps, and final counts (loaded/skipped/failed). The error log is stored as JSON.

`lineage.molecule_provenance` records which loader added each molecule, keyed on `(inchikey, source_name)`. This makes it possible to trace any molecule back to its origin and re-run specific enrichments.

### Ontology (`onto.*`)

`onto.reaction_classes` is a self-referencing hierarchy of reaction types (Suzuki coupling, amide bond formation, etc.) linked by RXNO identifiers and SMARTS patterns. `onto.hazard_data` stores GHS classifications per molecule (H-codes, signal word, pictograms).

## Data Pipeline

### Source Data

The primary data source is the [Open Reaction Database](https://github.com/open-reaction-database/ord-data) (~2.3 million reactions stored as Protocol Buffer files). Secondary enrichment comes from PubChem REST API, ChEBI OBO ontology, ChEMBL SQLite dumps, and PubChem GHS classifications.

### Loader Architecture

All loaders extend `BaseLoader`, which handles:

1. Creating a `lineage.data_loads` record at the start
2. Iterating `extract()` → `transform_one()` → batching → `load_batch()`
3. Flushing every `batch_size` rows (default 5000)
4. Tracking loaded/skipped/failed counts
5. Finalising the provenance record on completion or failure

#### ORD Loader

Reads `.pb.gz` protobuf files via `ord_schema.proto.reaction_pb2`. For each reaction:

1. Parses the ORD reaction message
2. Iterates over inputs/outcomes to extract individual compounds
3. Converts each compound's SMILES to a canonical form via RDKit (`Chem.MolToSmiles(Chem.MolFromSmiles(raw))`)
4. Computes the InChIKey from the canonical mol
5. Calculates molecular descriptors (MW, LogP, TPSA, HBA, HBD, rotatable bonds, ring count) using RDKit
6. Maps the ORD `ReactionRole` enum to our schema role strings (REACTANT→reactant, BYPRODUCT→product, WORKUP→additive, etc.)
7. Converts all units to SI-ish: temperature→Celsius, pressure→bar, time→seconds, mass→grams, volume→mL
8. Bulk upserts molecules with `ON CONFLICT (inchikey) DO NOTHING`, then inserts reactions, components, and conditions

#### Enrichment Loaders

- **PubChem:** Queries PubChem PUG REST API in batches of 100 InChIKeys. Fills in IUPAC name, CID, exact mass, XLogP, complexity. Respects the 5 req/sec rate limit.
- **ChEBI:** Downloads the ChEBI OBO ontology, parses it with `pronto`, extracts InChI strings from xrefs, and maps them to molecules via InChIKey.
- **ChEMBL:** Reads a local ChEMBL SQLite database. Extracts bioactivity records (IC50, Ki, EC50 values) and inserts them into `chem.bioactivities`.
- **GHS:** Fetches GHS hazard classifications from PubChem and inserts them into `onto.hazard_data`.

#### Fingerprint Backfill

A separate step populates the `mol` column (RDKit cartridge mol objects from SMILES) and Morgan fingerprints. This runs after the ORD load because the cartridge's `mol_from_smiles()` function is faster in bulk than computing during the initial load.

### Graph Building

Three-phase process run via CLI:

1. **`load graph`** — Creates `:Molecule` and `:Reaction` nodes from relational data, then creates edges for each reaction component based on role.
2. **`load materialise`** — Creates `SIMILAR_TO` edges from pgvector KNN results, `PRECURSOR_OF` shortcut edges from multi-step path traversal, and annotates molecule nodes with GHS hazard properties.

Both phases are idempotent. The graph can be rebuilt from scratch with `--rebuild`.

### Load Sequence

```bash
chemworldmodel init                  # run Alembic migrations
chemworldmodel load ord --data-dir /path/to/ord-data
chemworldmodel load fingerprints     # mol column + Morgan FPs
chemworldmodel load pubchem          # IUPAC names, CIDs
chemworldmodel load chebi            # ChEBI IDs, roles
chemworldmodel load chembl --db-path /path/to/chembl.db
chemworldmodel load ghs              # hazard data
chemworldmodel load graph            # AGE nodes + edges
chemworldmodel load materialise      # SIMILAR_TO, PRECURSOR_OF
```

## PostgreSQL Image

The database runs a custom Docker image built from `postgres:17-trixie` (Debian 13) in a multi-stage Dockerfile. Stage 1 compiles all four extensions from source against PG 17 headers:

| Extension | Version | Build Time | Purpose |
|-----------|---------|-----------|---------|
| pgvector | 0.8.2 | ~30s | HNSW index for Morgan fingerprint similarity (Jaccard distance on bit vectors = Tanimoto) |
| Apache AGE | 1.7.0 | ~2-3min | Property graph storage and openCypher queries. v1.7.0 requires PG 17+ |
| TimescaleDB | 2.26.0 | ~3-5min | Time-series partitioning (optional, currently unused) |
| RDKit Cartridge | Release_2026_03_1 | ~20-40min | `mol` type, substructure search via GiST, `mol_from_smiles()`, `morganbv_fp()` |

Stage 2 copies only the compiled `.so` files, SQL definitions, and RDKit shared libraries into a clean PG 17 image. Runtime dependencies are just the Boost 1.83 shared libraries that the RDKit cartridge links against.

AGE and TimescaleDB are set as `shared_preload_libraries`. The init script (`init.sql`) creates all extensions, loads the AGE shared library, creates the `chemworld` graph, and creates the five application schemas.

## Backend

### API (FastAPI)

The API server runs on port 8000 with these endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/query` | Natural language → SQL → results → grounded answer |
| GET | `/api/molecules/browse` | Paginated molecule listing with name search |
| GET | `/api/molecules/search` | Substructure search (RDKit) or similarity search (pgvector) |
| GET | `/api/molecules/{inchikey}` | Full molecule detail with hazards, bioactivities, reactions, similar molecules |
| GET | `/api/reactions/browse` | Paginated reaction listing with SMILES search |
| GET | `/api/reactions/search` | Filter by class, yield range, temperature range, atmosphere |
| GET | `/api/reactions/{reaction_id}` | Full reaction detail with components and conditions |
| GET | `/api/graph/routes/{inchikey}` | Retrosynthetic routes from commercially available starting materials |
| GET | `/api/graph/stats` | Graph node/edge counts |

All database calls are synchronous SQLAlchemy operations wrapped in `asyncio.to_thread()` to avoid blocking the event loop.

### NL-to-SQL Query Pipeline

The `/api/query` endpoint accepts a natural language chemistry question and returns a grounded answer. The pipeline:

1. **SQL generation** — Sends the question to an LLM (Gemini 2.5 Flash by default) with a system prompt containing the full schema documentation and 13 few-shot examples covering relational queries, Cypher graph traversal, similarity search, and hybrid SQL+Cypher patterns. Requests structured JSON output (`{sql, explanation}`), falls back to regex extraction from text if structured output fails.

2. **Validation** — Checks the generated SQL against a blocklist: no DML/DDL keywords (INSERT, DROP, ALTER...), no dangerous functions (dblink, lo_export, pg_read_file...), no system schema access (pg_catalog, information_schema), no multi-statement injection. Only SELECT and WITH (CTEs) are allowed. Max 2000 characters.

3. **Execution** — Runs the SQL in a read-only transaction with a 30-second statement timeout. Uses `exec_driver_sql()` instead of SQLAlchemy's `text()` to avoid misinterpreting Cypher edge syntax (`:REACTANT_IN`) as bind parameters. The connection pre-loads AGE and sets the search path to include `ag_catalog` and all application schemas.

4. **Answer grounding** — Sends the question, SQL, and raw results to the LLM for synthesis into a natural language answer with citations. The LLM is instructed to only state facts supported by the query results.

The LLM provider is configurable via environment variables: `gemini` (default, uses `google-genai` SDK), `openai`, or `ollama` (both use the `openai` SDK, ollama with a local base URL).

### CLI

Entry point: `chemworldmodel` (registered in pyproject.toml).

| Command | Description |
|---------|-------------|
| `init` | Run Alembic migrations to create/update schema |
| `stats` | Print row counts for all main tables |
| `load ord` | Ingest ORD protobuf files |
| `load fingerprints` | Backfill mol column and Morgan fingerprints |
| `load pubchem` | Enrich molecules from PubChem REST API |
| `load chebi` | Load ChEBI ontology mappings |
| `load chembl` | Load ChEMBL bioactivity data from SQLite |
| `load ghs` | Load GHS hazard classifications |
| `load graph` | Build AGE graph from relational data |
| `load materialise` | Create SIMILAR_TO, PRECURSOR_OF edges and hazard annotations |
| `query "..."` | Run a natural language query from the terminal |

## Frontend

Next.js 16 app on port 3000.

- **Home** (`/`) — Natural language query bar with example questions. Results display as molecule cards (when the data contains InChIKeys and SMILES) or a raw data table with linked identifiers.
- **Browse** (`/browse`) — Tabbed interface for browsing molecules and reactions with search and pagination.
- **Molecule detail** (`/molecules/[inchikey]`) — Structure rendering via RDKit.js WASM, property table, tabs for reactions/bioactivities/hazards/similar molecules. SSR.
- **Reaction detail** (`/reactions/[id]`) — Reaction scheme with per-component structure rendering, conditions, provenance. SSR.
- **Graph explorer** (`/graph?target={inchikey}`) — Interactive retrosynthetic route visualization using Cytoscape.js with breadthfirst layout. Configurable search depth (2–16 steps) and max routes. Clicking a molecule node searches for its routes.

Molecule structures are rendered client-side by loading the RDKit WASM module (~14 MB, lazy-loaded) and calling `get_mol(smiles).get_svg()`. The WASM binary is copied to `/public/rdkit/` at install time.

## Running

```bash
# Full stack
docker compose up -d

# Bootstrap schema and load data
docker compose exec api chemworldmodel init
docker compose exec api chemworldmodel load ord --data-dir /data/ord-data
docker compose exec api chemworldmodel load fingerprints
docker compose exec api chemworldmodel load graph
docker compose exec api chemworldmodel load materialise

# Enrichment (optional, requires external data)
docker compose exec api chemworldmodel load pubchem
docker compose exec api chemworldmodel load chebi
docker compose exec api chemworldmodel load chembl --db-path /data/chembl.db
docker compose exec api chemworldmodel load ghs
```

The API is at `http://localhost:8000`, the frontend at `http://localhost:3000`.

## Local Development

```bash
# Python (uses uv, manages Python 3.12 automatically)
uv sync --dev
uv run pytest tests/ -v
uv run ruff check .
uv run mypy chemworldmodel/

# Frontend
cd web && npm install && npm run dev

# API with hot reload
uv run uvicorn chemworldmodel.api.app:app --reload
```

## Project Layout

```
chemworldmodel/
  config.py                 # pydantic-settings: DB URL, LLM provider, timeouts
  db/
    engine.py               # SQLAlchemy engine factory (sync, connection pooling)
    schema.py               # all tables as SQLAlchemy Core Table objects
    migrations/             # Alembic (hand-written, not autogenerated)
  models/                   # Pydantic response models (molecules, reactions, graph, query)
  loaders/
    base.py                 # BaseLoader ABC with extract/transform/load + provenance
    ord_loader.py           # ORD protobuf → molecules + reactions
    pubchem_loader.py       # PubChem REST API enrichment
    chebi_loader.py         # ChEBI OBO ontology
    chembl_loader.py        # ChEMBL SQLite → bioactivities
    ghs_loader.py           # GHS hazard classifications
    fingerprints.py         # mol column + Morgan FP backfill
    classify.py             # SMARTS-based reaction classification
  graph/
    builder.py              # relational → AGE nodes + edges
    routes.py               # retrosynthetic route search via Cypher
    materialise.py          # SIMILAR_TO, PRECURSOR_OF edge creation
  query/
    nl_to_sql.py            # LLM-based NL→SQL pipeline + validation + execution
    prompts.py              # system prompts, schema context, few-shot examples
    similarity.py           # pgvector Tanimoto similarity search
  api/
    app.py                  # FastAPI app, CORS, /health, /api/query
    routes/                 # molecules, reactions, graph routers
  cli/
    main.py                 # Click CLI entry point
web/                        # Next.js 16 frontend
docker/
  postgres/
    Dockerfile              # PG 17 + 4 extensions, multi-stage build
    init.sql                # extension creation, graph init, schema creation
  Dockerfile.api            # Python API container
  Dockerfile.web            # Next.js container
docker-compose.yml          # db, api, web services
```
