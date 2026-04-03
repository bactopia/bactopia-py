"""Tests for bactopia.parsers.coverage."""

import pytest

from bactopia.parsers.coverage import read_coverage


class TestReadCoverage:
    def test_single_format(self, parser_fixtures):
        result = read_coverage(str(parser_fixtures / "coverage.txt"), format="single")
        assert "chr1" in result
        assert result["chr1"]["length"] == 5
        assert result["chr1"]["positions"] == [10, 20, 15, 30, 25]

    def test_tabbed_format(self, parser_fixtures):
        result = read_coverage(
            str(parser_fixtures / "coverage_tabbed.txt"), format="tabbed"
        )
        assert "chr1" in result
        assert result["chr1"]["length"] == 3
        assert result["chr1"]["positions"] == [10, 20, 15]

    def test_length_mismatch_exits(self, tmp_path):
        bad = tmp_path / "bad.txt"
        bad.write_text("##contig=<ID=chr1,length=10>\n5\n10\n")
        with pytest.raises(SystemExit):
            read_coverage(str(bad))
