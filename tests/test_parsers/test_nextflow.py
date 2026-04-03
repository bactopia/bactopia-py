"""Tests for bactopia.parsers.nextflow."""

import pytest

from bactopia.parsers.nextflow import parse


class TestParse:
    def test_base_config(self, parser_fixtures):
        path = str(parser_fixtures / "nextflow" / "base.config")
        result = parse(path, "test", "base")
        assert result["name"] == "test"
        assert "contents" in result
        assert "cpus = 1" in result["contents"]

    def test_params_config(self, parser_fixtures):
        path = str(parser_fixtures / "nextflow" / "params.config")
        result = parse(path, "test", "params")
        assert result["name"] == "test"
        assert "test_param1 = 90" in result["contents"]
        # params should NOT include the "params {" wrapper line
        assert "params {" not in result["contents"]

    def test_process_config(self, parser_fixtures):
        path = str(parser_fixtures / "nextflow" / "process.config")
        result = parse(path, "test", "process")
        assert result["name"] == "test"
        assert "TEST" in result["contents"]
        assert "process {" not in result["contents"]

    def test_profiles_config(self, parser_fixtures):
        path = str(parser_fixtures / "nextflow" / "profiles.config")
        result = parse(path, "test", "profiles")
        assert result["name"] == "test"
        assert "profiles {" in result["contents"]

    def test_invalid_file_type(self, parser_fixtures):
        path = str(parser_fixtures / "nextflow" / "base.config")
        with pytest.raises(ValueError, match="Unknown file_type"):
            parse(path, "test", "invalid")
