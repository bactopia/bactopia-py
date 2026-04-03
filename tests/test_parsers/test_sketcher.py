"""Tests for bactopia.parsers.sketcher."""

from bactopia.parsers.sketcher import parse


class TestParse:
    def test_returns_sample(self, parser_fixtures):
        """The current parse() function is a stub that returns sample only."""
        result = parse(str(parser_fixtures / "sample.tsv"), "sample1")
        assert result == {"sample": "sample1"}
