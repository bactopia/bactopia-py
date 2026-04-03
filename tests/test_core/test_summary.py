"""Tests for bactopia.summary (get_rank, print_failed, print_cutoffs)."""

import pytest

from bactopia.summary import get_rank, print_cutoffs, print_failed


class TestGetRank:
    """Tests for the QC ranking logic."""

    def test_gold(self, rank_cutoff):
        rank, reason = get_rank(rank_cutoff, 150, 35, 100, 50, 2800000, True)
        assert rank == "gold"
        assert reason == "passed all cutoffs"

    def test_gold_at_boundary(self, rank_cutoff):
        rank, reason = get_rank(rank_cutoff, 100, 30, 95, 100, 2800000, True)
        assert rank == "gold"

    def test_silver(self, rank_cutoff):
        rank, reason = get_rank(rank_cutoff, 75, 25, 80, 150, 2800000, True)
        assert rank == "silver"
        assert "Low coverage" in reason

    def test_bronze(self, rank_cutoff):
        rank, reason = get_rank(rank_cutoff, 30, 15, 50, 300, 2800000, True)
        assert rank == "bronze"

    def test_exclude_below_all(self, rank_cutoff):
        rank, reason = get_rank(rank_cutoff, 5, 5, 20, 1000, 2800000, True)
        assert rank == "exclude"

    def test_single_end_cannot_be_gold(self, rank_cutoff):
        """Single-end reads should never be gold even with gold-level stats."""
        rank, reason = get_rank(rank_cutoff, 150, 35, 100, 50, 2800000, False)
        assert rank != "gold"

    def test_single_end_cannot_be_silver(self, rank_cutoff):
        """Single-end reads with silver-level stats should be bronze."""
        rank, reason = get_rank(rank_cutoff, 75, 25, 80, 150, 2800000, False)
        assert rank == "bronze"
        assert "Single-end reads" in reason

    def test_single_end_bronze(self, rank_cutoff):
        rank, reason = get_rank(rank_cutoff, 30, 15, 50, 300, 2800000, False)
        assert rank == "bronze"
        assert "Single-end reads" in reason

    def test_multiple_reasons_sorted(self, rank_cutoff):
        """Reasons should be sorted alphabetically and joined by semicolons."""
        # Silver range but below gold: coverage=75 (< gold 100), quality=25 (< gold 30)
        rank, reason = get_rank(rank_cutoff, 75, 25, 80, 150, 2800000, True)
        assert rank == "silver"
        reasons = reason.split(";")
        assert len(reasons) > 1
        assert reasons == sorted(reasons)

    def test_min_assembled_size(self, rank_cutoff):
        rank_cutoff["min-assembled-size"] = 1000000
        rank, reason = get_rank(rank_cutoff, 150, 35, 100, 50, 500000, True)
        assert "Assembled size is too small" in reason

    def test_max_assembled_size(self, rank_cutoff):
        rank_cutoff["max-assembled-size"] = 5000000
        rank, reason = get_rank(rank_cutoff, 150, 35, 100, 50, 3000000, True)
        assert "Assembled size is too large" in reason

    def test_reason_empty_for_gold(self, rank_cutoff):
        rank, reason = get_rank(rank_cutoff, 150, 35, 100, 50, 2800000, True)
        assert reason == "passed all cutoffs"


class TestPrintFailed:
    def test_empty(self):
        assert print_failed({}) == ""

    def test_with_entries(self):
        failed = {
            "low-read-count": ["s1", "s2"],
            "genome-size": ["s3"],
            "failed-cutoff": ["s4"],
        }
        result = print_failed(failed)
        assert "Low Read Count: 2" in result
        assert "Genome Size: 1" in result
        # failed-cutoff should be excluded
        assert "Failed Cutoff" not in result

    def test_custom_spaces(self):
        failed = {"low-read-count": ["s1"]}
        result = print_failed(failed, spaces=4)
        assert result.startswith("    ")


class TestPrintCutoffs:
    def test_empty(self):
        assert print_cutoffs({}) == ""

    def test_with_entries(self):
        cutoffs = {"coverage": 5, "quality": 3}
        result = print_cutoffs(cutoffs)
        assert "coverage: 5" in result
        assert "quality: 3" in result

    def test_custom_spaces(self):
        cutoffs = {"coverage": 5}
        result = print_cutoffs(cutoffs, spaces=4)
        assert result.startswith("    ")
