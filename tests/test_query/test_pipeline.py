"""Integration tests for the NLToSQL pipeline with mocked LLM."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chemworldmodel.config import Settings
from chemworldmodel.models.query import LLMSQLResponse, QueryResult
from chemworldmodel.query.nl_to_sql import NLToSQL, SQLValidationError


@pytest.fixture
def mock_settings():
    return Settings(
        llm_provider="gemini",
        llm_api_key="test-key",
        llm_model="claude-sonnet-4-6",
        query_timeout=30,
        query_max_sql_chars=2000,
    )


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    result_mock = MagicMock()
    result_mock.keys.return_value = ["reaction_id", "yield_pct"]
    result_mock.fetchall.return_value = [
        ("ord-abc123", 85.0),
        ("ord-def456", 92.0),
    ]
    conn.execute.return_value = result_mock

    return engine


class TestNLToSQLPipeline:
    """Pipeline end-to-end tests with mocked LLM and DB."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self, mock_engine, mock_settings):
        pipeline = NLToSQL(engine=mock_engine, settings=mock_settings)

        sql_response = LLMSQLResponse(
            sql="SELECT r.reaction_id, r.yield_pct FROM rxn.reactions r LIMIT 50",
            explanation="Simple query",
        )
        synthesis_response = "Found 2 reactions with yields of 85% and 92%."

        with patch(
            "chemworldmodel.query.nl_to_sql._call_llm",
            new_callable=AsyncMock,
            side_effect=[sql_response, synthesis_response],
        ):
            result = await pipeline.query("What are the yields?")

        assert isinstance(result, QueryResult)
        assert result.answer == synthesis_response
        assert result.reaction_count == 2
        assert "ord-abc123" in result.citations
        assert "ord-def456" in result.citations

    @pytest.mark.asyncio
    async def test_validation_error_propagates(self, mock_engine, mock_settings):
        pipeline = NLToSQL(engine=mock_engine, settings=mock_settings)

        sql_response = LLMSQLResponse(
            sql="DROP TABLE rxn.reactions",
            explanation="oops",
        )

        with (
            patch(
                "chemworldmodel.query.nl_to_sql._call_llm",
                new_callable=AsyncMock,
                return_value=sql_response,
            ),
            pytest.raises(SQLValidationError),
        ):
            await pipeline.query("Drop all tables")

    @pytest.mark.asyncio
    async def test_zero_results(self, mock_settings):
        engine = MagicMock()
        conn = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        result_mock = MagicMock()
        result_mock.keys.return_value = ["reaction_id"]
        result_mock.fetchall.return_value = []
        conn.execute.return_value = result_mock

        pipeline = NLToSQL(engine=engine, settings=mock_settings)

        sql_response = LLMSQLResponse(
            sql="SELECT r.reaction_id FROM rxn.reactions r WHERE r.reaction_class = 'nonexistent'",
            explanation="Search",
        )

        with patch(
            "chemworldmodel.query.nl_to_sql._call_llm",
            new_callable=AsyncMock,
            side_effect=[sql_response, "I found some reactions."],
        ):
            result = await pipeline.query("Find nonexistent reactions")

        assert "couldn't find data" in result.answer
        assert result.reaction_count == 0

    @pytest.mark.asyncio
    async def test_fallback_sql_extraction(self, mock_engine, mock_settings):
        """If structured output fails, fall back to text extraction."""
        pipeline = NLToSQL(engine=mock_engine, settings=mock_settings)

        text_with_sql = (
            "Here is the SQL:\n"
            "```sql\n"
            "SELECT r.reaction_id, r.yield_pct FROM rxn.reactions r LIMIT 50\n"
            "```"
        )
        synthesis = "Found reactions."

        with patch(
            "chemworldmodel.query.nl_to_sql._call_llm",
            new_callable=AsyncMock,
            side_effect=[RuntimeError("Structured output failed"), text_with_sql, synthesis],
        ):
            result = await pipeline.query("Get yields")

        assert isinstance(result, QueryResult)
        assert result.reaction_count == 2


class TestExtractSqlFallback:
    """Test SQL extraction from freeform LLM text."""

    def test_sql_fenced_block(self):
        from chemworldmodel.query.nl_to_sql import _extract_sql_fallback

        text = "Here:\n```sql\nSELECT * FROM rxn.reactions\n```"
        assert _extract_sql_fallback(text) == "SELECT * FROM rxn.reactions"

    def test_generic_fenced_block(self):
        from chemworldmodel.query.nl_to_sql import _extract_sql_fallback

        text = "```\nSELECT 1\n```"
        assert _extract_sql_fallback(text) == "SELECT 1"

    def test_bare_select(self):
        from chemworldmodel.query.nl_to_sql import _extract_sql_fallback

        text = "SELECT * FROM rxn.reactions LIMIT 10"
        assert _extract_sql_fallback(text) == text

    def test_no_sql_raises(self):
        from chemworldmodel.query.nl_to_sql import _extract_sql_fallback

        with pytest.raises(SQLValidationError, match="Could not extract"):
            _extract_sql_fallback("I don't know how to help with that.")
