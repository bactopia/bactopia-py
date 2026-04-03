"""Tests for bactopia.parsers.gather."""

from bactopia.parsers.gather import parse


class TestParse:
    def test_returns_dict(self, parser_fixtures):
        result = parse(str(parser_fixtures / "gather_meta.tsv"), "sample1")
        assert isinstance(result, dict)

    def test_contains_sample(self, parser_fixtures):
        result = parse(str(parser_fixtures / "gather_meta.tsv"), "sample1")
        assert result["sample"] == "sample1"

    def test_contains_species(self, parser_fixtures):
        result = parse(str(parser_fixtures / "gather_meta.tsv"), "sample1")
        assert result["species"] == "Staphylococcus aureus"
