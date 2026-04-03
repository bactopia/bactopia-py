"""Tests for bactopia.parsers.error."""

from pathlib import Path

from bactopia.parsers.error import parse_errors


class TestParseErrors:
    def test_known_error_types(self, parser_fixtures):
        error_dir = parser_fixtures / "error_files"
        result = parse_errors(error_dir, "sample1")
        assert len(result) == 2
        types = {e["error_type"] for e in result}
        assert "low-read-count" in types
        assert "genome-size" in types

    def test_known_error_descriptions(self, parser_fixtures):
        error_dir = parser_fixtures / "error_files"
        result = parse_errors(error_dir, "sample1")
        for error in result:
            assert "Undocumented" not in error["description"]

    def test_unknown_error_type(self, tmp_path):
        (tmp_path / "sample1-unknown-thing-error.txt").write_text("")
        result = parse_errors(tmp_path, "sample1")
        assert len(result) == 1
        assert "Undocumented" in result[0]["description"]

    def test_no_errors(self, tmp_path):
        result = parse_errors(tmp_path, "sample1")
        assert result == []
