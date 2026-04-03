"""Tests for bactopia.parsers.versions."""

from bactopia.parsers.versions import parse_versions


class TestParseVersions:
    def test_basic(self, parser_fixtures):
        result = parse_versions([str(parser_fixtures / "versions.yml")], "sample1")
        assert isinstance(result, list)
        assert len(result) == 2

    def test_fields(self, parser_fixtures):
        result = parse_versions([str(parser_fixtures / "versions.yml")], "sample1")
        entry = result[0]
        assert "sample" in entry
        assert "process" in entry
        assert "tool" in entry
        assert "version" in entry

    def test_values(self, parser_fixtures):
        result = parse_versions([str(parser_fixtures / "versions.yml")], "sample1")
        tools = {e["tool"]: e for e in result}
        assert tools["spades"]["version"] == "3.15.5"
        assert tools["spades"]["process"] == "ASSEMBLER"
        assert tools["csvtk"]["version"] == "0.27.2"
