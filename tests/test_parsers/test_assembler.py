"""Tests for bactopia.parsers.assembler."""

from bactopia.parsers.assembler import parse


class TestParse:
    def test_returns_dict(self, parser_fixtures):
        result = parse(str(parser_fixtures / "assembler.tsv"), "sample1")
        assert isinstance(result, dict)

    def test_has_sample_key(self, parser_fixtures):
        result = parse(str(parser_fixtures / "assembler.tsv"), "sample1")
        assert result["sample"] == "sample1"

    def test_prefixes_keys(self, parser_fixtures):
        result = parse(str(parser_fixtures / "assembler.tsv"), "sample1")
        for key in result:
            if key != "sample":
                assert key.startswith("assembler_")

    def test_values_parsed(self, parser_fixtures):
        result = parse(str(parser_fixtures / "assembler.tsv"), "sample1")
        assert result["assembler_total_contig"] == "42"
        assert result["assembler_total_bp"] == "2850000"
