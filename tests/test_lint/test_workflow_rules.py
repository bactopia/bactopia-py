"""Tests for W021 and S025 lint rules (reject Value<Path> wrapper)."""

from bactopia.lint.rules.workflow_rules import rule_w021
from bactopia.lint.rules.subworkflow_rules import rule_s025


def _wf_ctx(params):
    """Build a minimal ctx dict for workflow rules with a params block."""
    return {
        "structure": {
            "wf_params_block": {
                "exists": True,
                "first_param": "rundir",
                "first_param_line": "    rundir : String",
                "params": [
                    {"name": "rundir", "type": "String", "colon_col": 11, "line_num": 2},
                    *params,
                ],
            }
        }
    }


def _sw_ctx(take_inputs):
    """Build a minimal ctx dict for subworkflow rules with take inputs."""
    return {"structure": {"sw_take_inputs": take_inputs}}


# ── W021 tests ──────────────────────────────────────────────────────────


class TestW021:
    def test_pass_no_path_params(self):
        ctx = _wf_ctx([
            {"name": "use_bakta", "type": "Boolean", "colon_col": 14, "line_num": 3},
        ])
        results = rule_w021("test", ctx)
        assert len(results) == 1
        assert results[0].is_pass()

    def test_pass_bare_path(self):
        ctx = _wf_ctx([
            {"name": "kraken2_db", "type": "Path", "colon_col": 15, "line_num": 3},
            {"name": "adapters", "type": "Path?", "colon_col": 15, "line_num": 4},
        ])
        results = rule_w021("test", ctx)
        assert len(results) == 1
        assert results[0].is_pass()

    def test_fail_value_path(self):
        ctx = _wf_ctx([
            {"name": "kraken2_db", "type": "Value<Path>", "colon_col": 15, "line_num": 3},
        ])
        results = rule_w021("test", ctx)
        assert len(results) == 1
        assert results[0].is_fail()
        assert "Path" in results[0].message

    def test_fail_value_path_nullable(self):
        ctx = _wf_ctx([
            {"name": "adapters", "type": "Value<Path?>", "colon_col": 15, "line_num": 3},
        ])
        results = rule_w021("test", ctx)
        assert len(results) == 1
        assert results[0].is_fail()
        assert "Path?" in results[0].message

    def test_fail_mixed(self):
        ctx = _wf_ctx([
            {"name": "kraken2_db", "type": "Path", "colon_col": 15, "line_num": 3},
            {"name": "adapters", "type": "Value<Path?>", "colon_col": 15, "line_num": 4},
            {"name": "reference", "type": "Value<Path>", "colon_col": 15, "line_num": 5},
        ])
        results = rule_w021("test", ctx)
        assert len(results) == 2
        assert all(r.is_fail() for r in results)
        names = [r.message for r in results]
        assert any("adapters" in m for m in names)
        assert any("reference" in m for m in names)

    def test_no_params_block(self):
        ctx = {"structure": {"wf_params_block": {"exists": False, "params": []}}}
        results = rule_w021("test", ctx)
        assert results == []


# ── S025 tests ──────────────────────────────────────────────────────────


class TestS025:
    def test_pass_bare_path(self):
        ctx = _sw_ctx([
            {"name": "database", "type": "Path", "line_num": 3},
            {"name": "proteins", "type": "Path?", "line_num": 4},
        ])
        results = rule_s025("test", ctx)
        assert len(results) == 1
        assert results[0].is_pass()

    def test_fail_value_path(self):
        ctx = _sw_ctx([
            {"name": "database", "type": "Value<Path>", "line_num": 3},
        ])
        results = rule_s025("test", ctx)
        assert len(results) == 1
        assert results[0].is_fail()
        assert "Path" in results[0].message

    def test_fail_value_path_nullable(self):
        ctx = _sw_ctx([
            {"name": "database", "type": "Value<Path?>", "line_num": 3},
        ])
        results = rule_s025("test", ctx)
        assert len(results) == 1
        assert results[0].is_fail()
        assert "Path?" in results[0].message

    def test_no_take_inputs(self):
        ctx = _sw_ctx([])
        results = rule_s025("test", ctx)
        assert results == []

    def test_non_path_types_ignored(self):
        ctx = _sw_ctx([
            {"name": "reads", "type": "Channel<Record>", "line_num": 2},
            {"name": "database", "type": "Path", "line_num": 3},
        ])
        results = rule_s025("test", ctx)
        assert len(results) == 1
        assert results[0].is_pass()
