"""Tests for bactopia.parsers.mlst."""

from bactopia.parsers.mlst import parse


class TestParse:
    def test_headerless_tsv(self, parser_fixtures):
        result = parse(str(parser_fixtures / "mlst_no_header.tsv"), "sample1")
        assert result["sample"] == "sample1"
        assert result["mlst_scheme"] == "saureus"
        assert result["mlst_st"] == "239"
