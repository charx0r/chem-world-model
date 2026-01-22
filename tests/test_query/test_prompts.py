"""Tests for prompt assembly in the NL-to-SQL pipeline."""

from chemworldmodel.query.prompts import (
    EXAMPLE_QUERIES,
    SCHEMA_CONTEXT,
    SYNTHESIS_PROMPT,
    build_sql_generation_prompt,
    build_synthesis_prompt,
)


class TestSchemaContext:
    """Schema context must include all required tables and instructions."""

    def test_contains_molecules_table(self):
        assert "chem.molecules" in SCHEMA_CONTEXT

    def test_contains_reactions_table(self):
        assert "rxn.reactions" in SCHEMA_CONTEXT

    def test_contains_reaction_components_table(self):
        assert "rxn.reaction_components" in SCHEMA_CONTEXT

    def test_contains_reaction_conditions_table(self):
        assert "rxn.reaction_conditions" in SCHEMA_CONTEXT

    def test_contains_onto_table(self):
        assert "onto.reaction_classes" in SCHEMA_CONTEXT

    def test_contains_rdkit_functions(self):
        assert "substruct" in SCHEMA_CONTEXT
        assert "morganbv_fp" in SCHEMA_CONTEXT
        assert "mol_from_smiles" in SCHEMA_CONTEXT

    def test_contains_pgvector_operator(self):
        assert "<%>" in SCHEMA_CONTEXT

    def test_contains_role_values(self):
        for role in ("reactant", "product", "catalyst", "solvent"):
            assert role in SCHEMA_CONTEXT

    def test_contains_key_columns(self):
        for col in ("inchikey", "reaction_id", "yield_pct", "reaction_class"):
            assert col in SCHEMA_CONTEXT

    def test_mentions_select_only(self):
        assert "SELECT" in SCHEMA_CONTEXT


class TestExampleQueries:
    """Few-shot examples must be well-formed."""

    def test_minimum_example_count(self):
        assert len(EXAMPLE_QUERIES) >= 8

    def test_all_have_question_and_sql(self):
        for ex in EXAMPLE_QUERIES:
            assert "question" in ex
            assert "sql" in ex

    def test_all_sql_start_with_select(self):
        for ex in EXAMPLE_QUERIES:
            assert ex["sql"].strip().upper().startswith("SELECT"), (
                f"Example SQL does not start with SELECT: {ex['question']}"
            )

    def test_examples_include_reaction_id(self):
        has_reaction_id = sum(1 for ex in EXAMPLE_QUERIES if "reaction_id" in ex["sql"])
        assert has_reaction_id >= len(EXAMPLE_QUERIES) // 2


class TestBuildSqlGenerationPrompt:
    """SQL generation prompt builder."""

    def test_returns_tuple(self):
        system, user = build_sql_generation_prompt("What catalysts?")
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_system_includes_schema(self):
        system, _ = build_sql_generation_prompt("test")
        assert "chem.molecules" in system

    def test_system_includes_examples(self):
        system, _ = build_sql_generation_prompt("test")
        assert "Example 1:" in system

    def test_user_includes_question(self):
        _, user = build_sql_generation_prompt("What solvents work best?")
        assert "What solvents work best?" in user


class TestBuildSynthesisPrompt:
    """Answer synthesis prompt builder."""

    def test_returns_tuple(self):
        system, user = build_synthesis_prompt("test", "SELECT 1", [{"a": 1}])
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_system_is_synthesis_prompt(self):
        system, _ = build_synthesis_prompt("test", "SELECT 1", [])
        assert system == SYNTHESIS_PROMPT

    def test_user_includes_question_and_sql(self):
        _, user = build_synthesis_prompt("What yields?", "SELECT yield_pct", [])
        assert "What yields?" in user
        assert "SELECT yield_pct" in user

    def test_truncates_large_results(self):
        results = [{"reaction_id": f"ord-{i:08d}", "yield_pct": i} for i in range(100)]
        _, user = build_synthesis_prompt("test", "SELECT 1", results)
        assert "80 more rows" in user
