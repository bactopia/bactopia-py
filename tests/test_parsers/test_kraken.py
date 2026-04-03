"""Tests for bactopia.parsers.kraken."""

from bactopia.parsers.kraken import bracken_root_count, kraken2_unclassified_count


class TestKraken2UnclassifiedCount:
    def test_returns_float(self, parser_fixtures):
        result = kraken2_unclassified_count(str(parser_fixtures / "kraken2_report.txt"))
        assert result == 500.0

    def test_no_unclassified(self, tmp_path):
        report = tmp_path / "no_u.txt"
        report.write_text("100.00\t1000\t0\tR\t1\troot\n")
        result = kraken2_unclassified_count(str(report))
        assert result is None


class TestBrackenRootCount:
    def test_returns_float(self, parser_fixtures):
        result = bracken_root_count(str(parser_fixtures / "bracken_report.txt"))
        assert result == 500.0

    def test_no_root(self, tmp_path):
        report = tmp_path / "no_root.txt"
        report.write_text("100.00\t1000\t1000\tS\t1280\tStaph\n")
        result = bracken_root_count(str(report))
        assert result is None
