"""Tests for bactopia.parsers.workflows (catalog graph walking)."""

import json

from bactopia.parsers.workflows import get_modules_by_workflow


class TestGetModulesByWorkflow:
    def test_basic(self, parser_fixtures):
        with open(parser_fixtures / "catalog.json") as f:
            catalog = json.load(f)
        result = get_modules_by_workflow("testwf", catalog)
        assert "mod_a" in result
        assert "mod_b" in result
        assert "mod_c" in result

    def test_unknown_workflow(self, parser_fixtures):
        with open(parser_fixtures / "catalog.json") as f:
            catalog = json.load(f)
        result = get_modules_by_workflow("nonexistent", catalog)
        assert result == []

    def test_deduplication(self):
        catalog = {
            "workflows": {"wf": {"subworkflows": ["sw1", "sw2"]}},
            "subworkflows": {
                "sw1": {"calls": {"modules": ["shared_mod"], "subworkflows": []}},
                "sw2": {"calls": {"modules": ["shared_mod"], "subworkflows": []}},
            },
        }
        result = get_modules_by_workflow("wf", catalog)
        assert result.count("shared_mod") == 1
