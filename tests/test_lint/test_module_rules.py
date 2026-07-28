"""Tests for MC016 (repo-vendored data paths must be anchored)."""

from bactopia.lint.rules.module_rules import rule_mc016

ANCHOR = "${params.bactopia_dir}"


def _ctx(params, bactopia_path=None):
    """Build a minimal ctx dict for MC016 with a parsed params block."""
    ctx = {
        "config": {
            "exists": True,
            "params": [
                {"name": name, "value": value, "ignores": ignores}
                for name, value, ignores in params
            ],
        }
    }
    if bactopia_path is not None:
        ctx["bactopia_path"] = bactopia_path
    return ctx


class TestMC016:
    def test_skipped_when_no_config(self):
        assert rule_mc016("modules/foo", {"config": {"exists": False}}) == []

    def test_skipped_when_no_path_like_params(self, tmp_path):
        ctx = _ctx(
            [
                ("foo_centre", "'Bactopia'", set()),
                ("foo_evalue", '"1e-09"', set()),
                ("foo_coverage", "80", set()),
                ("foo_db", "null", set()),
            ],
            tmp_path,
        )
        assert rule_mc016("modules/foo", ctx) == []

    def test_fail_launchdir_relative(self, tmp_path):
        ctx = _ctx([("foo_proteins", '"./data/proteins.faa"', set())], tmp_path)
        results = rule_mc016("modules/foo", ctx)
        assert len(results) == 1
        assert results[0].is_fail()
        assert "./data/proteins.faa" in results[0].message

    def test_fail_bare_relative_without_dot_slash(self, tmp_path):
        ctx = _ctx([("foo_db", '"data/db.tar.gz"', set())], tmp_path)
        results = rule_mc016("modules/foo", ctx)
        assert len(results) == 1
        assert results[0].is_fail()

    def test_fail_parent_relative(self, tmp_path):
        ctx = _ctx([("foo_db", '"../shared/db.txt"', set())], tmp_path)
        assert rule_mc016("modules/foo", ctx)[0].is_fail()

    def test_pass_anchored_and_present(self, tmp_path):
        target = tmp_path / "modules" / "foo" / "data" / "x.faa"
        target.parent.mkdir(parents=True)
        target.write_text("x")
        ctx = _ctx(
            [("foo_db", f'"{ANCHOR}/modules/foo/data/x.faa"', set())],
            tmp_path,
        )
        results = rule_mc016("modules/foo", ctx)
        assert len(results) == 1
        assert results[0].is_pass()

    def test_fail_anchored_but_missing(self, tmp_path):
        ctx = _ctx(
            [("foo_db", f'"{ANCHOR}/modules/foo/data/typo.faa"', set())],
            tmp_path,
        )
        results = rule_mc016("modules/foo", ctx)
        assert len(results) == 1
        assert results[0].is_fail()
        assert "modules/foo/data/typo.faa" in results[0].message

    def test_pass_absolute_path(self, tmp_path):
        ctx = _ctx([("foo_db", '"/opt/db/x.txt"', set())], tmp_path)
        assert rule_mc016("modules/foo", ctx)[0].is_pass()

    def test_pass_other_interpolated_anchor(self, tmp_path):
        ctx = _ctx([("foo_dir", '"${params.bactopia_cache}/foo"', set())], tmp_path)
        assert rule_mc016("modules/foo", ctx)[0].is_pass()

    def test_urls_are_not_paths(self, tmp_path):
        ctx = _ctx(
            [("foo_url", '"https://example.com/db.tar.gz"', set())],
            tmp_path,
        )
        assert rule_mc016("modules/foo", ctx) == []

    def test_inline_ignore_is_respected(self, tmp_path):
        ctx = _ctx([("foo_db", '"./data/db.txt"', {"MC016"})], tmp_path)
        assert rule_mc016("modules/foo", ctx) == []

    def test_reports_unanchored_and_missing_separately(self, tmp_path):
        ctx = _ctx(
            [
                ("foo_a", '"./data/a.txt"', set()),
                ("foo_b", f'"{ANCHOR}/modules/foo/data/b.txt"', set()),
            ],
            tmp_path,
        )
        results = rule_mc016("modules/foo", ctx)
        assert len(results) == 2
        assert all(r.is_fail() for r in results)
