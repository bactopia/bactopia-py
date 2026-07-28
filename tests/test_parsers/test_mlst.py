"""Tests for bactopia.parsers.mlst."""

from bactopia.parsers.mlst import parse


class TestParse:
    def test_scheme_and_st_are_reported(self, parser_fixtures):
        result = parse(str(parser_fixtures / "mlst.tsv"), "sample1")
        assert result["sample"] == "sample1"
        assert result["mlst_scheme"] == "saureus"
        assert result["mlst_st"] == "8"

    def test_header_is_not_reported_as_data(self, parser_fixtures):
        """`mlst --full` emits a header; it must never leak into the summary."""
        result = parse(str(parser_fixtures / "mlst.tsv"), "sample1")
        assert result["mlst_scheme"] != "SCHEME"
        assert result["mlst_st"] != "ST"

    def test_no_scheme_match(self, parser_fixtures):
        """A sample with no matching scheme reports '-' rather than failing."""
        result = parse(str(parser_fixtures / "mlst_no_call.tsv"), "sample2")
        assert result["sample"] == "sample2"
        assert result["mlst_scheme"] == "-"
        assert result["mlst_st"] == "-"
