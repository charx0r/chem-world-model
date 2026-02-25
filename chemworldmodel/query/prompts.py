"""LLM prompt templates for the NL-to-SQL query pipeline."""

from __future__ import annotations

import json
from typing import Any

SCHEMA_CONTEXT = """\
You are a SQL query generator for a chemistry reaction database running PostgreSQL 17 \
with RDKit cartridge and pgvector extensions.

## Tables

### chem.molecules
Primary table of chemical compounds. Primary key: inchikey (TEXT, 27-char InChIKey).
Columns:
- inchikey (TEXT PK) — globally unique molecular identifier
- canonical_smiles (TEXT NOT NULL) — RDKit-canonicalised SMILES
- inchi (TEXT) — full InChI string
- mol_formula (TEXT) — e.g. 'C6H12O6'
- mol_weight (FLOAT) — molecular weight in Da
- exact_mass (FLOAT)
- logp (FLOAT) — computed partition coefficient
- tpsa (FLOAT) — topological polar surface area
- hba (INTEGER) — hydrogen bond acceptors
- hbd (INTEGER) — hydrogen bond donors
- num_rotatable (INTEGER) — rotatable bonds
- num_rings (INTEGER) — ring count
- iupac_name (TEXT) — IUPAC systematic name (from PubChem enrichment)
- complexity (FLOAT) — PubChem complexity score
- mol (mol) — RDKit mol object (enables substructure search)
- fp_morgan (bit(2048)) — Morgan/ECFP4 fingerprint (radius 2, 2048 bits)
- sources (TEXT[]) — array e.g. ['ord', 'pubchem']
- cas_number (TEXT), chembl_id (TEXT), pubchem_cid (BIGINT), chebi_id (TEXT)
- commercially_available (BOOLEAN)
- created_at, updated_at (TIMESTAMPTZ)

### rxn.reactions
Experimentally observed chemical reactions. Primary key: reaction_id (TEXT).
Columns:
- reaction_id (TEXT PK) — e.g. 'ord-3a8f2c...'
- reaction_smiles (TEXT) — mapped reaction SMILES
- reaction_class (TEXT) — e.g. 'Suzuki coupling', 'amide bond formation'
- rxno_id (TEXT) — RXNO ontology identifier
- temperature_c (FLOAT) — temperature in Celsius
- pressure_bar (FLOAT) — pressure in bar
- time_seconds (INTEGER) — reaction time
- atmosphere (TEXT) — 'N2', 'Ar', 'air', or NULL
- yield_pct (FLOAT) — percentage yield 0-100
- yield_type (TEXT) — 'isolated', 'crude', 'calculated'
- selectivity (TEXT)
- procedure_text (TEXT) — original procedure description
- source (TEXT NOT NULL) — 'ord', 'uspto'
- source_id (TEXT), source_version (TEXT)
- patent_id (TEXT), doi (TEXT)
- created_at (TIMESTAMPTZ)

### rxn.reaction_components
Links molecules to reactions with roles. Join table.
Columns:
- id (BIGSERIAL PK)
- reaction_id (TEXT FK → rxn.reactions)
- inchikey (TEXT FK → chem.molecules)
- role (TEXT NOT NULL) — one of: 'reactant', 'product', 'catalyst', 'solvent', \
'reagent', 'base', 'acid', 'ligand', 'additive', 'internal_standard'
- stoichiometry (FLOAT), equivalents (FLOAT)
- mass_g (FLOAT), volume_ml (FLOAT)
- is_major (BOOLEAN) — for products: major vs minor
- yield_pct (FLOAT) — per-component yield
Unique constraint: (reaction_id, inchikey, role)

### rxn.reaction_conditions
Detailed reaction conditions (normalised).
Columns:
- id (BIGSERIAL PK)
- reaction_id (TEXT FK → rxn.reactions)
- condition_type (TEXT) — 'temperature', 'pressure', 'time', 'stirring', 'ph'
- value (FLOAT), unit (TEXT), precision (FLOAT)
- phase (TEXT) — 'initial', 'during', 'final'
Unique constraint: (reaction_id, condition_type, phase)

### chem.bioactivities
Bioactivity data from ChEMBL. Links molecules to biological targets.
Columns:
- id (BIGSERIAL PK)
- inchikey (TEXT FK → chem.molecules)
- target_chembl_id (TEXT NOT NULL) — ChEMBL target ID
- target_name (TEXT) — e.g. 'HERG', 'Cyclooxygenase-2'
- target_organism (TEXT) — e.g. 'Homo sapiens'
- activity_type (TEXT NOT NULL) — e.g. 'IC50', 'Ki', 'EC50'
- value (FLOAT) — activity value in standard units
- unit (TEXT) — e.g. 'nM', 'uM'
- relation (TEXT) — '=', '>', '<'
- assay_chembl_id (TEXT NOT NULL)
Unique constraint: (inchikey, target_chembl_id, activity_type, assay_chembl_id)

### onto.hazard_data
GHS hazard classifications (from PubChem).
Columns:
- inchikey (TEXT FK → chem.molecules)
- ghs_codes (TEXT[]) — array of H-codes, e.g. ARRAY['H225', 'H319']
- signal_word (TEXT) — 'Danger' or 'Warning'
- pictograms (TEXT[]) — array of GHS pictogram codes, e.g. ARRAY['GHS02', 'GHS07']
- source (TEXT) — default 'pubchem_ghs'
Primary key: (inchikey, source)

### onto.reaction_classes
Hierarchical taxonomy of reaction types.
Columns: class_id (TEXT PK), parent_id (TEXT FK self), name (TEXT), rxno_id (TEXT), \
description (TEXT), smarts_pattern (TEXT), level (INTEGER)

## Key relationships
- reaction_components is the central join table linking molecules to reactions with roles
- To find molecules in a reaction: JOIN rxn.reaction_components rc ON r.reaction_id = rc.reaction_id \
JOIN chem.molecules m ON rc.inchikey = m.inchikey
- Filter by role: WHERE rc.role = 'catalyst' (or 'reactant', 'product', 'solvent', etc.)
- To find bioactive molecules: JOIN chem.bioactivities b ON m.inchikey = b.inchikey
- To find hazardous molecules: JOIN onto.hazard_data h ON m.inchikey = h.inchikey
- For GHS code filtering, use ANY: WHERE 'H301' = ANY(h.ghs_codes)

## RDKit cartridge functions
- mol_from_smiles('CCO'::cstring) → mol object
- substruct(mol, 'c1ccccc1'::qmol) → boolean substructure match
- morganbv_fp(mol, 2, 2048) → bit(2048) Morgan fingerprint

## pgvector similarity
- fp_morgan <%> query_fp → Jaccard distance (= 1 - Tanimoto for binary fingerprints)
- To find similar molecules: WHERE fp_morgan <%> morganbv_fp(mol_from_smiles(:smiles::cstring), 2, 2048) < 0.3
- Tanimoto similarity = 1 - Jaccard distance

## Rules
1. ALWAYS return reaction_id in your SELECT for traceability
2. Use JOINs through reaction_components to connect molecules and reactions
3. For "best yield" queries, filter WHERE yield_pct IS NOT NULL
4. For molecular similarity, use the <%> operator on fp_morgan
5. LIMIT results to 50 unless the user specifies otherwise
6. Use ILIKE for case-insensitive text matching on reaction_class
7. yield_pct is 0-100, NOT 0-1
8. Output ONLY a single SELECT statement, no semicolons
9. For route/path queries, use the AGE graph via cypher() function (see below)

## Apache AGE Graph (chemworld)

The relational data is mirrored in an Apache AGE property graph named 'chemworld'.
Use the cypher() function for graph traversal queries (routes, paths, neighbours).

### Node types:
- :Molecule {inchikey, smiles, mol_formula, mol_weight, commercially_available}
- :Reaction {reaction_id, reaction_class, temperature_c, yield_pct, source}

### Edge types:
- (Molecule)-[:REACTANT_IN {stoichiometry, equivalents}]->(Reaction)
- (Reaction)-[:PRODUCT_OF {yield_pct, is_major}]->(Molecule)
- (Molecule)-[:CATALYSES {equivalents}]->(Reaction)
- (Molecule)-[:SOLVENT_IN {volume_ml}]->(Reaction)
- (Molecule)-[:SIMILAR_TO {tanimoto}]->(Molecule)
- (Molecule)-[:PRECURSOR_OF {step_count, cumulative_yield}]->(Molecule)

### Hybrid SQL+Cypher pattern:
Wrap Cypher in the cypher() function. Cast agtype outputs with ::text for JOINs:
```sql
SELECT route.rxn_id::text AS reaction_id, r.yield_pct
FROM cypher('chemworld', $$
    MATCH (start:Molecule {commercially_available: true})
        -[:REACTANT_IN]->(rxn:Reaction)
        -[:PRODUCT_OF]->(target:Molecule {inchikey: 'TARGET_INCHIKEY'})
    RETURN rxn.reaction_id
$$) AS route(rxn_id agtype)
JOIN rxn.reactions r ON r.reaction_id = route.rxn_id::text
```

### When to use graph vs SQL:
- Route/path finding, neighbours, connectivity → Cypher via cypher()
- Property filtering, aggregation, statistics → plain SQL
- Combine both: Cypher for traversal, JOIN with relational for filtering\
"""

EXAMPLE_QUERIES: list[dict[str, str]] = [
    {
        "question": "What solvents give the best yields for Suzuki couplings?",
        "sql": (
            "SELECT m.canonical_smiles AS solvent,\n"
            "       ROUND(AVG(r.yield_pct)::numeric, 1) AS avg_yield,\n"
            "       COUNT(*) AS reaction_count,\n"
            "       ARRAY_AGG(DISTINCT r.reaction_id) AS reaction_ids\n"
            "FROM rxn.reactions r\n"
            "JOIN rxn.reaction_components rc ON r.reaction_id = rc.reaction_id\n"
            "JOIN chem.molecules m ON rc.inchikey = m.inchikey\n"
            "WHERE rc.role = 'solvent'\n"
            "  AND r.reaction_class ILIKE '%suzuki%'\n"
            "  AND r.yield_pct IS NOT NULL\n"
            "GROUP BY m.canonical_smiles\n"
            "HAVING COUNT(*) >= 10\n"
            "ORDER BY avg_yield DESC\n"
            "LIMIT 20"
        ),
    },
    {
        "question": "What catalysts are used in Heck reactions?",
        "sql": (
            "SELECT m.canonical_smiles AS catalyst,\n"
            "       COUNT(DISTINCT r.reaction_id) AS reaction_count,\n"
            "       ROUND(AVG(r.yield_pct)::numeric, 1) AS avg_yield,\n"
            "       ARRAY_AGG(DISTINCT r.reaction_id ORDER BY r.reaction_id) AS reaction_ids\n"
            "FROM rxn.reactions r\n"
            "JOIN rxn.reaction_components rc ON r.reaction_id = rc.reaction_id\n"
            "JOIN chem.molecules m ON rc.inchikey = m.inchikey\n"
            "WHERE rc.role = 'catalyst'\n"
            "  AND r.reaction_class ILIKE '%heck%'\n"
            "GROUP BY m.canonical_smiles\n"
            "ORDER BY reaction_count DESC\n"
            "LIMIT 20"
        ),
    },
    {
        "question": "Show me the highest-yielding amide bond formations",
        "sql": (
            "SELECT r.reaction_id, r.reaction_smiles, r.yield_pct,\n"
            "       r.temperature_c, r.atmosphere\n"
            "FROM rxn.reactions r\n"
            "WHERE r.reaction_class ILIKE '%amide%bond%'\n"
            "  AND r.yield_pct IS NOT NULL\n"
            "ORDER BY r.yield_pct DESC\n"
            "LIMIT 50"
        ),
    },
    {
        "question": "What is the average yield at different temperatures for Grignard reactions?",
        "sql": (
            "SELECT ROUND(r.temperature_c / 10) * 10 AS temp_bucket,\n"
            "       ROUND(AVG(r.yield_pct)::numeric, 1) AS avg_yield,\n"
            "       COUNT(*) AS reaction_count,\n"
            "       ARRAY_AGG(r.reaction_id ORDER BY r.reaction_id LIMIT 5) AS sample_reaction_ids\n"
            "FROM rxn.reactions r\n"
            "WHERE r.reaction_class ILIKE '%grignard%'\n"
            "  AND r.yield_pct IS NOT NULL\n"
            "  AND r.temperature_c IS NOT NULL\n"
            "GROUP BY temp_bucket\n"
            "ORDER BY temp_bucket\n"
            "LIMIT 50"
        ),
    },
    {
        "question": "Find reactions that use benzene as a reactant",
        "sql": (
            "SELECT r.reaction_id, r.reaction_smiles, r.reaction_class, r.yield_pct\n"
            "FROM rxn.reaction_components rc\n"
            "JOIN chem.molecules m ON rc.inchikey = m.inchikey\n"
            "JOIN rxn.reactions r ON rc.reaction_id = r.reaction_id\n"
            "WHERE rc.role = 'reactant'\n"
            "  AND substruct(m.mol, 'c1ccccc1'::qmol)\n"
            "LIMIT 50"
        ),
    },
    {
        "question": "Find molecules similar to aspirin (CC(=O)Oc1ccccc1C(=O)O)",
        "sql": (
            "SELECT m.inchikey, m.canonical_smiles,\n"
            "       1 - (m.fp_morgan <%> morganbv_fp(\n"
            "           mol_from_smiles('CC(=O)Oc1ccccc1C(=O)O'::cstring), 2, 2048\n"
            "       )) AS tanimoto\n"
            "FROM chem.molecules m\n"
            "WHERE m.fp_morgan IS NOT NULL\n"
            "  AND m.fp_morgan <%> morganbv_fp(\n"
            "      mol_from_smiles('CC(=O)Oc1ccccc1C(=O)O'::cstring), 2, 2048\n"
            "  ) < 0.3\n"
            "ORDER BY m.fp_morgan <%> morganbv_fp(\n"
            "    mol_from_smiles('CC(=O)Oc1ccccc1C(=O)O'::cstring), 2, 2048\n"
            ")\n"
            "LIMIT 50"
        ),
    },
    {
        "question": "How many reactions are in the database by source?",
        "sql": (
            "SELECT r.source, COUNT(*) AS reaction_count,\n"
            "       ROUND(AVG(r.yield_pct)::numeric, 1) AS avg_yield,\n"
            "       MIN(r.reaction_id) AS sample_reaction_id\n"
            "FROM rxn.reactions r\n"
            "GROUP BY r.source\n"
            "ORDER BY reaction_count DESC"
        ),
    },
    {
        "question": "What reactions use both Pd catalyst and DMF solvent with yield above 80%?",
        "sql": (
            "SELECT DISTINCT r.reaction_id, r.reaction_class, r.yield_pct,\n"
            "       r.temperature_c\n"
            "FROM rxn.reactions r\n"
            "JOIN rxn.reaction_components rc_cat ON r.reaction_id = rc_cat.reaction_id\n"
            "JOIN chem.molecules m_cat ON rc_cat.inchikey = m_cat.inchikey\n"
            "JOIN rxn.reaction_components rc_sol ON r.reaction_id = rc_sol.reaction_id\n"
            "JOIN chem.molecules m_sol ON rc_sol.inchikey = m_sol.inchikey\n"
            "WHERE rc_cat.role = 'catalyst'\n"
            "  AND m_cat.canonical_smiles ILIKE '%Pd%'\n"
            "  AND rc_sol.role = 'solvent'\n"
            "  AND m_sol.canonical_smiles ILIKE '%DMF%'\n"
            "  AND r.yield_pct > 80\n"
            "ORDER BY r.yield_pct DESC\n"
            "LIMIT 50"
        ),
    },
    {
        "question": "What are the most common reaction classes in the database?",
        "sql": (
            "SELECT r.reaction_class, COUNT(*) AS reaction_count,\n"
            "       ROUND(AVG(r.yield_pct)::numeric, 1) AS avg_yield,\n"
            "       ARRAY_AGG(r.reaction_id ORDER BY r.reaction_id LIMIT 3) AS sample_reaction_ids\n"
            "FROM rxn.reactions r\n"
            "WHERE r.reaction_class IS NOT NULL\n"
            "GROUP BY r.reaction_class\n"
            "ORDER BY reaction_count DESC\n"
            "LIMIT 20"
        ),
    },
    {
        "question": "What are the one-step synthesis routes to aspirin from commercially available starting materials?",
        "sql": (
            "SELECT route.start_ik::text AS start_inchikey,\n"
            "       route.start_smiles::text AS start_smiles,\n"
            "       route.rxn_id::text AS reaction_id,\n"
            "       r.yield_pct, r.reaction_class\n"
            "FROM cypher('chemworld', $$\n"
            "    MATCH (s:Molecule {commercially_available: true})\n"
            "        -[:REACTANT_IN]->(rxn:Reaction)\n"
            "        -[:PRODUCT_OF]->(t:Molecule {inchikey: 'BSYNRYMUTXBXSQ-UHFFFAOYSA-N'})\n"
            "    RETURN s.inchikey, s.smiles, rxn.reaction_id\n"
            "$$) AS route(start_ik agtype, start_smiles agtype, rxn_id agtype)\n"
            "JOIN rxn.reactions r ON r.reaction_id = route.rxn_id::text\n"
            "WHERE r.yield_pct IS NOT NULL\n"
            "ORDER BY r.yield_pct DESC\n"
            "LIMIT 20"
        ),
    },
    {
        "question": "Which molecules are most similar to ethanol in the graph?",
        "sql": (
            "SELECT route.neighbor_ik::text AS inchikey,\n"
            "       route.neighbor_smiles::text AS smiles,\n"
            "       route.tanimoto::float AS tanimoto\n"
            "FROM cypher('chemworld', $$\n"
            "    MATCH (m:Molecule {inchikey: 'LFQSCWFLJHTTHZ-UHFFFAOYSA-N'})\n"
            "        -[s:SIMILAR_TO]-(n:Molecule)\n"
            "    RETURN n.inchikey, n.smiles, s.tanimoto\n"
            "$$) AS route(neighbor_ik agtype, neighbor_smiles agtype, tanimoto agtype)\n"
            "ORDER BY route.tanimoto::float DESC\n"
            "LIMIT 20"
        ),
    },
    {
        "question": "Which molecules have IC50 activity below 100 nM?",
        "sql": (
            "SELECT m.inchikey, m.canonical_smiles, m.iupac_name,\n"
            "       b.target_name, b.activity_type, b.value, b.unit\n"
            "FROM chem.bioactivities b\n"
            "JOIN chem.molecules m ON b.inchikey = m.inchikey\n"
            "WHERE b.activity_type = 'IC50'\n"
            "  AND b.value < 100\n"
            "  AND b.unit = 'nM'\n"
            "ORDER BY b.value ASC\n"
            "LIMIT 50"
        ),
    },
    {
        "question": "Which molecules have GHS danger classification?",
        "sql": (
            "SELECT m.inchikey, m.canonical_smiles, m.iupac_name,\n"
            "       h.signal_word, h.ghs_codes, h.pictograms\n"
            "FROM onto.hazard_data h\n"
            "JOIN chem.molecules m ON h.inchikey = m.inchikey\n"
            "WHERE h.signal_word = 'Danger'\n"
            "LIMIT 50"
        ),
    },
    {
        "question": "Show reactions with yields over 95% that run under nitrogen atmosphere",
        "sql": (
            "SELECT r.reaction_id, r.reaction_class, r.yield_pct,\n"
            "       r.temperature_c, r.time_seconds\n"
            "FROM rxn.reactions r\n"
            "WHERE r.yield_pct > 95\n"
            "  AND r.atmosphere = 'N2'\n"
            "ORDER BY r.yield_pct DESC\n"
            "LIMIT 50"
        ),
    },
]


SYNTHESIS_PROMPT = """\
You are a chemistry research assistant. You have been given:
1. A user's chemistry question
2. The SQL query that was executed against a reaction database
3. The raw results from that query

Your task: write a concise, informative natural language answer based ONLY on the query results.

CRITICAL RULES:
- ONLY state facts that are directly supported by the query results
- NEVER use your training knowledge to generate chemistry facts
- If the results are empty, say "I couldn't find data matching your question in the database."
- Include key statistics: counts, averages, ranges where relevant
- Reference specific reaction_ids as citations using the format [reaction_id]
- Keep the answer to 2-4 sentences for simple queries, up to a paragraph for complex ones
- Use precise chemical language\
"""


def _format_examples() -> str:
    """Format few-shot examples for the SQL generation prompt."""
    parts: list[str] = []
    for i, ex in enumerate(EXAMPLE_QUERIES, 1):
        parts.append(f"Example {i}:")
        parts.append(f"Question: {ex['question']}")
        parts.append(f"SQL:\n{ex['sql']}")
        parts.append("")
    return "\n".join(parts)


def build_sql_generation_prompt(question: str) -> tuple[str, str]:
    """Build system and user prompts for SQL generation.

    Returns (system_prompt, user_message).
    """
    system = f"{SCHEMA_CONTEXT}\n\n## Examples\n\n{_format_examples()}"
    user = (
        f"Generate a single PostgreSQL SELECT query to answer this question:\n\n"
        f"{question}\n\n"
        f"Return ONLY the SQL and a brief explanation of your approach."
    )
    return system, user


def build_synthesis_prompt(
    question: str,
    sql: str,
    results: list[dict[str, Any]],
) -> tuple[str, str]:
    """Build system and user prompts for answer synthesis.

    Truncates results to first 20 rows if needed.
    Returns (system_prompt, user_message).
    """
    total_rows = len(results)
    display_results = results[:20]

    results_text = json.dumps(display_results, indent=2, default=str)
    if total_rows > 20:
        results_text += f"\n\n... and {total_rows - 20} more rows (total: {total_rows})"

    user = (
        f"Question: {question}\n\n"
        f"SQL executed:\n{sql}\n\n"
        f"Results ({total_rows} rows):\n{results_text}"
    )
    return SYNTHESIS_PROMPT, user
