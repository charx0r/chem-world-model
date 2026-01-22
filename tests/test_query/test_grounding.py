"""Tests for answer grounding and citation extraction."""

from chemworldmodel.query.grounding import (
    _compute_statistics,
    _extract_reaction_ids,
    ground_answer,
)


class TestExtractReactionIds:
    """Reaction ID extraction from result rows."""

    def test_direct_reaction_id(self):
        results = [
            {"reaction_id": "ord-abc123", "yield_pct": 85.0},
            {"reaction_id": "ord-def456", "yield_pct": 90.0},
        ]
        ids = _extract_reaction_ids(results)
        assert ids == ["ord-abc123", "ord-def456"]

    def test_deduplication(self):
        results = [
            {"reaction_id": "ord-abc123"},
            {"reaction_id": "ord-abc123"},
            {"reaction_id": "ord-def456"},
        ]
        ids = _extract_reaction_ids(results)
        assert ids == ["ord-abc123", "ord-def456"]

    def test_array_agg_reaction_ids(self):
        results = [
            {"solvent": "DMSO", "reaction_ids": ["ord-aaa", "ord-bbb"]},
            {"solvent": "THF", "reaction_ids": ["ord-ccc"]},
        ]
        ids = _extract_reaction_ids(results)
        assert set(ids) == {"ord-aaa", "ord-bbb", "ord-ccc"}

    def test_no_reaction_ids(self):
        results = [{"mol_weight": 180.0}, {"mol_weight": 250.0}]
        ids = _extract_reaction_ids(results)
        assert ids == []

    def test_none_values_skipped(self):
        results = [
            {"reaction_id": None},
            {"reaction_id": "ord-abc123"},
        ]
        ids = _extract_reaction_ids(results)
        assert ids == ["ord-abc123"]

    def test_empty_results(self):
        assert _extract_reaction_ids([]) == []


class TestComputeStatistics:
    """Aggregate statistics computation."""

    def test_yield_stats(self):
        results = [
            {"yield_pct": 80.0},
            {"yield_pct": 90.0},
            {"yield_pct": 70.0},
        ]
        stats = _compute_statistics(results)
        assert stats["row_count"] == 3
        assert stats["yield_pct"]["avg"] == 80.0
        assert stats["yield_pct"]["min"] == 70.0
        assert stats["yield_pct"]["max"] == 90.0

    def test_skips_none_values(self):
        results = [
            {"yield_pct": 80.0},
            {"yield_pct": None},
            {"yield_pct": 90.0},
        ]
        stats = _compute_statistics(results)
        assert stats["yield_pct"]["count"] == 2

    def test_empty_results(self):
        stats = _compute_statistics([])
        assert stats["row_count"] == 0

    def test_no_numeric_columns(self):
        results = [{"reaction_id": "ord-abc"}, {"reaction_id": "ord-def"}]
        stats = _compute_statistics(results)
        assert stats["row_count"] == 2
        assert "yield_pct" not in stats


class TestGroundAnswer:
    """Full grounding pipeline."""

    def test_zero_results_overrides_answer(self):
        result = ground_answer([], "Some hallucinated answer", "SELECT 1")
        assert "couldn't find data" in result.answer
        assert result.reaction_count == 0
        assert result.citations == []

    def test_normal_grounding(self):
        raw = [
            {"reaction_id": "ord-111", "yield_pct": 85.0},
            {"reaction_id": "ord-222", "yield_pct": 92.0},
        ]
        result = ground_answer(raw, "The average yield is 88.5%.", "SELECT ...")
        assert result.answer == "The average yield is 88.5%."
        assert result.sql == "SELECT ..."
        assert result.reaction_count == 2
        assert "ord-111" in result.citations
        assert "ord-222" in result.citations
        assert len(result.raw_data) == 2

    def test_citation_cap(self):
        raw = [{"reaction_id": f"ord-{i:06d}"} for i in range(200)]
        result = ground_answer(raw, "Many reactions.", "SELECT ...")
        assert len(result.citations) == 50
        assert result.reaction_count == 200

    def test_raw_data_cap(self):
        raw = [{"reaction_id": f"ord-{i:06d}", "yield_pct": float(i)} for i in range(200)]
        result = ground_answer(raw, "Many reactions.", "SELECT ...")
        assert len(result.raw_data) == 100
