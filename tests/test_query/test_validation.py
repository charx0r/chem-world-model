"""Tests for SQL validation in the NL-to-SQL pipeline."""

import pytest

from chemworldmodel.query.nl_to_sql import SQLValidationError, _validate_sql


class TestValidSelectQueries:
    """Valid queries should pass validation."""

    def test_simple_select(self):
        sql = "SELECT * FROM rxn.reactions LIMIT 10"
        assert _validate_sql(sql) == sql

    def test_join_query(self):
        sql = (
            "SELECT r.reaction_id, m.canonical_smiles "
            "FROM rxn.reactions r "
            "JOIN rxn.reaction_components rc ON r.reaction_id = rc.reaction_id "
            "JOIN chem.molecules m ON rc.inchikey = m.inchikey "
            "WHERE rc.role = 'catalyst' LIMIT 50"
        )
        result = _validate_sql(sql)
        assert result.startswith("SELECT")

    def test_aggregate_query(self):
        sql = (
            "SELECT r.reaction_class, COUNT(*) AS cnt, "
            "ROUND(AVG(r.yield_pct)::numeric, 1) AS avg_yield "
            "FROM rxn.reactions r "
            "GROUP BY r.reaction_class ORDER BY cnt DESC LIMIT 20"
        )
        assert _validate_sql(sql)

    def test_substructure_search(self):
        sql = (
            "SELECT m.inchikey, m.canonical_smiles "
            "FROM chem.molecules m "
            "WHERE substruct(m.mol, 'c1ccccc1'::qmol) LIMIT 50"
        )
        assert _validate_sql(sql)

    def test_similarity_search(self):
        sql = (
            "SELECT m.inchikey, 1 - (m.fp_morgan <%> morganbv_fp("
            "mol_from_smiles('CCO'::cstring), 2, 2048)) AS tanimoto "
            "FROM chem.molecules m "
            "WHERE m.fp_morgan IS NOT NULL LIMIT 50"
        )
        assert _validate_sql(sql)

    def test_onto_schema_access(self):
        sql = "SELECT class_id, name FROM onto.reaction_classes LIMIT 50"
        assert _validate_sql(sql)

    def test_lineage_schema_access(self):
        sql = "SELECT load_id, source_name, status FROM lineage.data_loads"
        assert _validate_sql(sql)

    def test_trailing_semicolon_stripped(self):
        sql = "SELECT * FROM rxn.reactions LIMIT 10;"
        result = _validate_sql(sql)
        assert not result.endswith(";")

    def test_lowercase_select(self):
        sql = "select reaction_id from rxn.reactions limit 10"
        assert _validate_sql(sql)


class TestBlockedKeywords:
    """DML/DDL keywords must be rejected."""

    def test_insert(self):
        with pytest.raises(SQLValidationError, match="INSERT"):
            _validate_sql("INSERT INTO rxn.reactions VALUES ('test')")

    def test_update(self):
        with pytest.raises(SQLValidationError, match="UPDATE"):
            _validate_sql("UPDATE rxn.reactions SET yield_pct = 100")

    def test_delete(self):
        with pytest.raises(SQLValidationError, match="DELETE"):
            _validate_sql("DELETE FROM rxn.reactions")

    def test_drop(self):
        with pytest.raises(SQLValidationError, match="DROP"):
            _validate_sql("DROP TABLE rxn.reactions")

    def test_alter(self):
        with pytest.raises(SQLValidationError, match="ALTER"):
            _validate_sql("ALTER TABLE rxn.reactions ADD COLUMN foo TEXT")

    def test_create(self):
        with pytest.raises(SQLValidationError, match="CREATE"):
            _validate_sql("CREATE TABLE evil (id INT)")

    def test_truncate(self):
        with pytest.raises(SQLValidationError, match="TRUNCATE"):
            _validate_sql("TRUNCATE rxn.reactions")

    def test_grant(self):
        with pytest.raises(SQLValidationError, match="GRANT"):
            _validate_sql("GRANT ALL ON rxn.reactions TO evil_user")

    def test_copy(self):
        with pytest.raises(SQLValidationError, match="COPY"):
            _validate_sql("COPY rxn.reactions TO '/tmp/evil.csv'")


class TestNotSelectFirst:
    """Non-SELECT-first statements must be rejected."""

    def test_with_cte_then_insert(self):
        with pytest.raises(SQLValidationError, match="Only SELECT"):
            _validate_sql("WITH data AS (SELECT 1) INSERT INTO evil VALUES (1)")

    def test_empty_string(self):
        with pytest.raises(SQLValidationError, match="Empty"):
            _validate_sql("")

    def test_whitespace_only(self):
        with pytest.raises(SQLValidationError, match="Empty"):
            _validate_sql("   ")


class TestSemicolonInjection:
    """Mid-query semicolons must be rejected."""

    def test_multi_statement(self):
        with pytest.raises(SQLValidationError, match="semicolons"):
            _validate_sql("SELECT 1; DROP TABLE rxn.reactions")

    def test_semicolon_in_subquery(self):
        with pytest.raises(SQLValidationError, match="semicolons"):
            _validate_sql("SELECT * FROM (SELECT 1; SELECT 2) t")


class TestSchemaRestrictions:
    """Only chem, rxn, onto, lineage schemas allowed."""

    def test_pg_catalog_blocked(self):
        with pytest.raises(SQLValidationError, match="pg_catalog"):
            _validate_sql("SELECT * FROM pg_catalog.pg_tables")

    def test_information_schema_blocked(self):
        with pytest.raises(SQLValidationError, match="information_schema"):
            _validate_sql("SELECT * FROM information_schema.tables")

    def test_public_schema_blocked(self):
        with pytest.raises(SQLValidationError, match="not in the allowed"):
            _validate_sql("SELECT * FROM public.users")


class TestDangerousFunctions:
    """Dangerous PostgreSQL functions must be rejected."""

    def test_dblink(self):
        with pytest.raises(SQLValidationError, match="dblink"):
            _validate_sql("SELECT * FROM dblink('host=evil', 'SELECT 1')")

    def test_pg_read_file(self):
        with pytest.raises(SQLValidationError, match="pg_read_file"):
            _validate_sql("SELECT pg_read_file('/etc/passwd')")

    def test_lo_export(self):
        with pytest.raises(SQLValidationError, match="lo_export"):
            _validate_sql("SELECT lo_export(1234, '/tmp/evil')")


class TestCommentHiding:
    """Keywords hidden in comments must still be caught after comment stripping."""

    def test_line_comment_hiding(self):
        # The DROP is in a comment, but after stripping the remaining text
        # might not be valid SELECT
        sql = "-- SELECT\nDROP TABLE rxn.reactions"
        with pytest.raises(SQLValidationError):
            _validate_sql(sql)

    def test_block_comment_hiding(self):
        sql = "SELECT /* DROP TABLE rxn.reactions */ * FROM rxn.reactions LIMIT 10"
        # This is actually valid — the DROP is in a comment and gets stripped
        result = _validate_sql(sql)
        assert "DROP" not in result


class TestLengthLimit:
    """SQL exceeding character limit must be rejected."""

    def test_over_limit(self):
        sql = "SELECT * FROM rxn.reactions WHERE " + "reaction_id = 'x' OR " * 200
        with pytest.raises(SQLValidationError, match="character limit"):
            _validate_sql(sql, max_chars=500)

    def test_at_limit(self):
        sql = "SELECT * FROM rxn.reactions LIMIT 10"
        # Should pass with a generous limit
        assert _validate_sql(sql, max_chars=5000)
