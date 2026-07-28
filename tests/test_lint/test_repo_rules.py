"""Tests for bactopia.lint.rules.repo_rules (V001 version consistency)."""

from bactopia.lint.rules.repo_rules import rule_v001, rule_v002, rule_v003


def _seed(tmp, bactopia="4.1.0", plugin="2.1.6", citation="4.1.0", pin="2.1.6"):
    (tmp / "versions.yml").write_text(f"bactopia: {bactopia}\nnf-bactopia: {plugin}\n")
    (tmp / "nextflow.config").write_text(
        f"manifest {{\n    version = '{bactopia}'\n}}\n"
        f"params.bactopia_version = '{bactopia}'\n"
        f"plugins {{\n    id 'nf-bactopia@{pin}'\n}}\n"
    )
    (tmp / "bin").mkdir()
    (tmp / "bin" / "bactopia").write_text(f"#!/usr/bin/env bash\nVERSION={bactopia}\n")
    (tmp / "data" / "conda").mkdir(parents=True)
    (tmp / "data" / "conda" / "meta.yaml").write_text(
        f"{{% set version = '{bactopia}' %}}\n"
    )
    (tmp / "CITATION.cff").write_text(f"cff-version: 1.2.0\nversion: {citation}\n")


def test_all_match_passes(tmp_path):
    _seed(tmp_path)
    results = rule_v001("repo", {"bactopia_path": tmp_path})
    assert len(results) == 1
    assert results[0].is_pass()


def test_citation_lag_fails(tmp_path):
    _seed(tmp_path, citation="4.0.0")
    results = rule_v001("repo", {"bactopia_path": tmp_path})
    assert results[0].is_fail()
    assert "CITATION.cff" in results[0].message


def test_plugin_pin_drift_fails(tmp_path):
    _seed(tmp_path, pin="2.1.5")
    results = rule_v001("repo", {"bactopia_path": tmp_path})
    assert results[0].is_fail()
    assert "2.1.5" in results[0].message


def test_missing_versions_yml_fails(tmp_path):
    results = rule_v001("repo", {"bactopia_path": tmp_path})
    assert results[0].is_fail()
    assert "versions.yml" in results[0].message


def test_bactopia_version_drift_in_test_config_fails(tmp_path):
    _seed(tmp_path)
    d = tmp_path / "modules" / "foo" / "tests"
    d.mkdir(parents=True)
    (d / "nextflow.config").write_text("params {\n    bactopia_version = '4.0.0'\n}\n")
    results = rule_v001("repo", {"bactopia_path": tmp_path})
    assert results[0].is_fail()
    assert "bactopia_version" in results[0].message
    assert "4.0.0" in results[0].message


def test_v002_changelog_matches_passes(tmp_path):
    (tmp_path / "versions.yml").write_text("bactopia: 4.1.0\nnf-bactopia: 2.1.6\n")
    (tmp_path / "CHANGELOG.md").write_text('## v4.1.0 bactopia "x" 2026/01/01\n')
    results = rule_v002("repo", {"bactopia_path": tmp_path})
    assert results[0].is_pass()


def test_v002_changelog_mismatch_fails(tmp_path):
    (tmp_path / "versions.yml").write_text("bactopia: 4.1.0\nnf-bactopia: 2.1.6\n")
    (tmp_path / "CHANGELOG.md").write_text('## v4.0.0 bactopia "x" 2026/01/01\n')
    results = rule_v002("repo", {"bactopia_path": tmp_path})
    assert results[0].is_fail()
    assert "4.0.0" in results[0].message


def test_v002_missing_changelog_fails(tmp_path):
    (tmp_path / "versions.yml").write_text("bactopia: 4.1.0\nnf-bactopia: 2.1.6\n")
    results = rule_v002("repo", {"bactopia_path": tmp_path})
    assert results[0].is_fail()


def _seed_v003(tmp_path, declared="2.1.6", latest="2.1.6", sibling=True):
    bp = tmp_path / "bactopia"
    bp.mkdir()
    (bp / "versions.yml").write_text(f"bactopia: 4.1.0\nnf-bactopia: {declared}\n")
    if sibling:
        nfb = tmp_path / "nf-bactopia"
        nfb.mkdir()
        (nfb / "build.gradle").write_text(f"version = '{latest}'\n")
    return bp


def test_v003_pin_current_passes(tmp_path):
    bp = _seed_v003(tmp_path, declared="2.1.6", latest="2.1.6")
    results = rule_v003("repo", {"bactopia_path": bp})
    assert results[0].is_pass()


def test_v003_pin_lags_warns(tmp_path):
    bp = _seed_v003(tmp_path, declared="2.1.6", latest="2.1.7")
    results = rule_v003("repo", {"bactopia_path": bp})
    assert results[0].is_warn()
    assert "2.1.7" in results[0].message


def test_v003_no_sibling_passes(tmp_path):
    bp = _seed_v003(tmp_path, sibling=False)
    results = rule_v003("repo", {"bactopia_path": bp})
    assert results[0].is_pass()
