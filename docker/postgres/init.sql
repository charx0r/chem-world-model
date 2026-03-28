-- ChemWorldModel: PostgreSQL extension and schema bootstrap
-- Runs automatically on first container start via docker-entrypoint-initdb.d

-- Extensions (order: pgvector before rdkit in case of type dependencies)
CREATE EXTENSION IF NOT EXISTS vector;          -- pgvector (extension name is "vector")
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS age;
CREATE EXTENSION IF NOT EXISTS rdkit;

-- Apache AGE: load shared library and create the reaction graph
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT create_graph('chemworld');

-- Application schemas
CREATE SCHEMA IF NOT EXISTS chem;       -- molecular data
CREATE SCHEMA IF NOT EXISTS rxn;        -- reaction data
CREATE SCHEMA IF NOT EXISTS onto;       -- ontology and classification
CREATE SCHEMA IF NOT EXISTS ingest;     -- loader staging tables
CREATE SCHEMA IF NOT EXISTS lineage;    -- provenance tracking
