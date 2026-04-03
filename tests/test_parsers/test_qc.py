"""Tests for bactopia.parsers.qc."""

from bactopia.parsers.qc import _merge_qc_stats, parse


class TestParse:
    def test_single_end(self, parser_fixtures):
        result = parse(str(parser_fixtures / "qc_single.json"), "sample1")
        assert result["sample"] == "sample1"
        assert "qc_final_is_paired" in result or "qc_original_is_paired" in result

    def test_paired_end(self, parser_fixtures):
        """Paired-end triggers when the base path doesn't exist but R1/R2 do."""
        # The fixture path should not exist as-is, but R1/R2 versions should
        path = str(parser_fixtures / "sample1-final.json")
        result = parse(path, "sample1")
        assert result["sample"] == "sample1"
        assert result.get("qc_final_is_paired") is True


class TestMergeQcStats:
    def test_coverage_summed(self):
        r1 = {
            "qc_stats": {
                "total_bp": 100,
                "coverage": 25.0,
                "read_total": 50,
                "qual_mean": 30.0,
            },
            "per_base_quality": [30],
            "read_lengths": [100],
        }
        r2 = {
            "qc_stats": {
                "total_bp": 100,
                "coverage": 25.0,
                "read_total": 50,
                "qual_mean": 28.0,
            },
            "per_base_quality": [28],
            "read_lengths": [100],
        }
        result = _merge_qc_stats(r1, r2)
        assert result["qc_stats"]["total_bp"] == 200
        assert result["qc_stats"]["coverage"] == 50.0
        assert result["qc_stats"]["read_total"] == 100

    def test_quality_averaged(self):
        r1 = {
            "qc_stats": {"qual_mean": 30.0},
            "per_base_quality": [30],
            "read_lengths": [100],
        }
        r2 = {
            "qc_stats": {"qual_mean": 28.0},
            "per_base_quality": [28],
            "read_lengths": [100],
        }
        result = _merge_qc_stats(r1, r2)
        assert result["qc_stats"]["qual_mean"] == "29.0000"

    def test_per_base_quality_kept_separate(self):
        r1 = {
            "qc_stats": {},
            "per_base_quality": [30, 31],
            "read_lengths": [100],
        }
        r2 = {
            "qc_stats": {},
            "per_base_quality": [28, 29],
            "read_lengths": [99],
        }
        result = _merge_qc_stats(r1, r2)
        assert result["r1_per_base_quality"] == [30, 31]
        assert result["r2_per_base_quality"] == [28, 29]
