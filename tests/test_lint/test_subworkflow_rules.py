"""Tests for S026/S027 lint rules (emit channel documentation)."""

from bactopia.lint.rules.subworkflow_rules import rule_s026, rule_s027


def _ctx(emit_channels, output_tags):
    """Build a minimal ctx dict for S026."""
    return {
        "groovydoc": {
            "has_doc": True,
            "tags": {"output": output_tags} if output_tags is not None else {},
        },
        "structure": {"emit_channels": emit_channels},
    }


class TestS026:
    def test_pass_all_emits_documented(self):
        ctx = _ctx(
            ["sample_outputs", "run_outputs", "alignment"],
            ["sample_outputs", "run_outputs", "alignment"],
        )
        results = rule_s026("test", ctx)
        assert len(results) == 1
        assert results[0].is_pass()

    def test_pass_output_tags_with_descriptions(self):
        ctx = _ctx(
            ["sample_outputs", "run_outputs", "alignment"],
            [
                "sample_outputs",
                "run_outputs",
                "alignment  Core-genome alignment for downstream analysis",
            ],
        )
        results = rule_s026("test", ctx)
        assert len(results) == 1
        assert results[0].is_pass()

    def test_fail_missing_downstream_emit(self):
        ctx = _ctx(
            ["sample_outputs", "run_outputs", "assembly", "assembly_reads"],
            ["sample_outputs", "run_outputs"],
        )
        results = rule_s026("test", ctx)
        assert len(results) == 1
        assert results[0].is_fail()
        assert "assembly" in results[0].message
        assert "assembly_reads" in results[0].message

    def test_warn_extra_output_tag(self):
        ctx = _ctx(
            ["sample_outputs", "run_outputs"],
            ["sample_outputs", "run_outputs", "alignment"],
        )
        results = rule_s026("test", ctx)
        assert len(results) == 1
        assert results[0].is_warn()
        assert "alignment" in results[0].message

    def test_fail_and_warn_combined(self):
        ctx = _ctx(
            ["sample_outputs", "run_outputs", "reads"],
            ["sample_outputs", "run_outputs", "alignment"],
        )
        results = rule_s026("test", ctx)
        assert len(results) == 2
        fail_results = [r for r in results if r.is_fail()]
        warn_results = [r for r in results if r.is_warn()]
        assert len(fail_results) == 1
        assert "reads" in fail_results[0].message
        assert len(warn_results) == 1
        assert "alignment" in warn_results[0].message

    def test_skip_no_groovydoc(self):
        ctx = {
            "groovydoc": {"has_doc": False, "tags": {}},
            "structure": {"emit_channels": ["sample_outputs"]},
        }
        results = rule_s026("test", ctx)
        assert results == []

    def test_skip_no_emit_channels(self):
        ctx = _ctx([], ["sample_outputs", "run_outputs"])
        results = rule_s026("test", ctx)
        assert results == []

    def test_skip_no_output_tags(self):
        ctx = _ctx(["sample_outputs", "run_outputs"], None)
        results = rule_s026("test", ctx)
        assert len(results) == 1
        assert results[0].is_fail()
        assert "sample_outputs" in results[0].message


def _s027_ctx(empty_channels, output_has_fields):
    """Build a minimal ctx dict for S027."""
    return {
        "groovydoc": {
            "has_doc": True,
            "doc_output_has_fields": output_has_fields,
        },
        "structure": {"empty_emit_channels": empty_channels},
    }


class TestS027:
    def test_pass_no_empty_channels(self):
        ctx = _s027_ctx(set(), {"sample_outputs": True, "run_outputs": True})
        results = rule_s027("test", ctx)
        assert len(results) == 1
        assert results[0].is_pass()

    def test_pass_empty_channel_no_fields(self):
        ctx = _s027_ctx(
            {"sample_outputs"},
            {"sample_outputs": False, "run_outputs": True},
        )
        results = rule_s027("test", ctx)
        assert len(results) == 1
        assert results[0].is_pass()

    def test_fail_empty_channel_with_fields(self):
        ctx = _s027_ctx(
            {"sample_outputs"},
            {"sample_outputs": True, "run_outputs": False},
        )
        results = rule_s027("test", ctx)
        assert len(results) == 1
        assert results[0].is_fail()
        assert "sample_outputs" in results[0].message

    def test_fail_multiple_empty_with_fields(self):
        ctx = _s027_ctx(
            {"sample_outputs", "run_outputs"},
            {"sample_outputs": True, "run_outputs": True},
        )
        results = rule_s027("test", ctx)
        assert len(results) == 2
        assert all(r.is_fail() for r in results)

    def test_skip_no_groovydoc(self):
        ctx = {
            "groovydoc": {"has_doc": False},
            "structure": {"empty_emit_channels": {"sample_outputs"}},
        }
        results = rule_s027("test", ctx)
        assert results == []

    def test_skip_empty_channel_not_in_output_tags(self):
        ctx = _s027_ctx({"sample_outputs"}, {})
        results = rule_s027("test", ctx)
        assert len(results) == 1
        assert results[0].is_pass()
