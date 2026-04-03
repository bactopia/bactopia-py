"""Tests for bactopia.parsers.amrfinderplus."""

from bactopia.parsers.amrfinderplus import parse


class TestParse:
    def test_returns_sample_and_hits(self, parser_fixtures):
        result = parse(str(parser_fixtures / "amrfinderplus.tsv"), "sample1")
        assert result["sample"] == "sample1"
        assert "amrfinderplus_hits" in result

    def test_hits_are_list(self, parser_fixtures):
        result = parse(str(parser_fixtures / "amrfinderplus.tsv"), "sample1")
        assert isinstance(result["amrfinderplus_hits"], list)
        assert len(result["amrfinderplus_hits"]) == 2

    def test_hit_fields(self, parser_fixtures):
        result = parse(str(parser_fixtures / "amrfinderplus.tsv"), "sample1")
        hit = result["amrfinderplus_hits"][0]
        assert hit["Gene symbol"] == "mecA"
