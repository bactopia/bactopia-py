"""Tests for bactopia.parsers.citations."""

from bactopia.parsers.citations import parse_citations


class TestParseCitations:
    def test_returns_list(self, parser_fixtures):
        result = parse_citations(str(parser_fixtures / "citations.yml"))
        assert isinstance(result, list)
        assert len(result) == 2

    def test_citations_dict(self, parser_fixtures):
        citations, module_citations = parse_citations(
            str(parser_fixtures / "citations.yml")
        )
        assert "bactopia" in citations
        assert "datasets" in citations

    def test_module_citations_lowered(self, parser_fixtures):
        citations, module_citations = parse_citations(
            str(parser_fixtures / "citations.yml")
        )
        assert "bactopia" in module_citations
        assert "ariba" in module_citations
        assert module_citations["bactopia"]["name"] == "Bactopia"
