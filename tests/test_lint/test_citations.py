"""Tests for bactopia.lint.citations.validate_citations."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from bactopia.cli.citations import citations as citations_cmd
from bactopia.lint.citations import validate_citations

CITATIONS_YML = """\
workflows:
  bactopia:
    name: Bactopia
    cite: |
      Placeholder citation for Bactopia.
tools:
  fastp:
    name: fastp
    cite: |
      Placeholder citation for fastp.
  unicycler:
    name: Unicycler
    cite: |
      Placeholder citation for Unicycler.
  orphan_tool:
    name: Orphan
    cite: |
      Placeholder citation for an orphan tool.
  nextflow:
    name: Nextflow
    provenance_only: true
    cite: |
      Placeholder citation for Nextflow.
"""

MODULE_MAIN_NF = """\
/**
 * fastp
 *
 * @status stable
 * @keywords qc, reads
 * @tags complexity:simple input-type:single output-type:single features:qc
 * @citation fastp
 */
process FASTP {
    input:
    val sample

    output:
    val sample

    script:
    ""
}
"""

SUBWORKFLOW_MAIN_NF = """\
/**
 * qc
 *
 * @status stable
 * @keywords qc
 * @tags complexity:simple input-type:single output-type:single features:qc
 * @citation fastp
 * @modules fastp
 */
workflow QC {
    take: ch_input
    main: ch_out = ch_input
    emit: ch_out
}
"""

WORKFLOW_MAIN_NF_GOOD = """\
/**
 * bactopia
 *
 * @status stable
 * @keywords main
 * @tags complexity:complex input-type:multiple output-type:multiple features:core
 * @citation bactopia, fastp, unicycler
 */
workflow BACTOPIA {
    main: ch_out = Channel.empty()
}
"""

WORKFLOW_MAIN_NF_BAD = """\
/**
 * rogue
 *
 * @status beta
 * @keywords rogue
 * @tags complexity:simple input-type:single output-type:single features:test
 * @citation fastp, not_a_real_key, also_missing
 */
workflow ROGUE {
    main: ch_out = Channel.empty()
}
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Build a minimal Bactopia-like repo tree under tmp_path."""
    _write(tmp_path / "data" / "citations.yml", CITATIONS_YML)
    _write(tmp_path / "modules" / "fastp" / "main.nf", MODULE_MAIN_NF)
    _write(tmp_path / "subworkflows" / "qc" / "main.nf", SUBWORKFLOW_MAIN_NF)
    _write(tmp_path / "workflows" / "bactopia" / "main.nf", WORKFLOW_MAIN_NF_GOOD)
    return tmp_path


class TestValidateCitations:
    def test_shape(self, repo):
        report = validate_citations(repo)
        assert set(report.keys()) == {
            "orphans",
            "expected_orphans",
            "potential_homes",
            "missing_workflow_keys",
            "summary",
        }
        assert set(report["summary"].keys()) == {
            "orphans_total",
            "expected_orphans_total",
            "missing_total",
            "yml_total",
            "referenced_total",
        }

    def test_detects_orphans(self, repo):
        report = validate_citations(repo)
        # `orphan_tool` is defined in yml but never cited.
        assert "orphan_tool" in report["orphans"]["tools"]
        # `fastp`, `unicycler`, and `bactopia` are all cited somewhere.
        assert "fastp" not in report["orphans"]["tools"]
        assert "unicycler" not in report["orphans"]["tools"]
        assert report["orphans"]["workflows"] == []
        # `nextflow` carries `provenance_only: true` so it belongs in the
        # expected bucket, not the orphan bucket.
        assert "nextflow" not in report["orphans"]["tools"]

    def test_provenance_only_unreferenced_is_expected(self, repo):
        report = validate_citations(repo)
        assert "nextflow" in report["expected_orphans"]["tools"]
        assert report["summary"]["expected_orphans_total"] == 1
        # Real orphans still fire — only `orphan_tool` in this fixture.
        assert report["summary"]["orphans_total"] == 1

    def test_provenance_only_referenced_is_not_expected(self, repo):
        # If a provenance_only entry IS cited somewhere, it's just a normal
        # reference — not an expected orphan and not a real orphan.
        _write(
            repo / "modules" / "nf_user" / "main.nf",
            MODULE_MAIN_NF.replace("@citation fastp", "@citation nextflow"),
        )
        report = validate_citations(repo)
        assert "nextflow" not in report["expected_orphans"]["tools"]
        assert "nextflow" not in report["orphans"]["tools"]
        assert report["summary"]["expected_orphans_total"] == 0

    def test_workflow_missing_keys_detected(self, repo):
        _write(repo / "workflows" / "rogue" / "main.nf", WORKFLOW_MAIN_NF_BAD)
        report = validate_citations(repo)
        missing_keys = {item["key"] for item in report["missing_workflow_keys"]}
        assert missing_keys == {"not_a_real_key", "also_missing"}

    def test_module_missing_keys_not_reported(self, repo):
        # Replace the module's @citation with a bogus key; M035 would catch this,
        # but validate_citations() scopes missing-key reporting to workflows.
        _write(
            repo / "modules" / "fastp" / "main.nf",
            MODULE_MAIN_NF.replace("@citation fastp", "@citation not_in_yml"),
        )
        report = validate_citations(repo)
        assert report["missing_workflow_keys"] == []

    def test_missing_keys_include_file_and_line(self, repo):
        _write(repo / "workflows" / "rogue" / "main.nf", WORKFLOW_MAIN_NF_BAD)
        report = validate_citations(repo)
        item = next(
            x for x in report["missing_workflow_keys"] if x["key"] == "not_a_real_key"
        )
        assert item["file"].endswith("workflows/rogue/main.nf")
        assert item["component"] == "workflows/rogue"
        assert item["line"] is not None and item["line"] > 0

    def test_clean_repo(self, repo):
        # The baseline `repo` fixture cites fastp, unicycler, and bactopia;
        # `orphan_tool` is unused and `nextflow` is provenance_only. After
        # adding a reference to orphan_tool, real orphans are gone even
        # though nextflow still sits in the expected_orphans bucket.
        _write(
            repo / "modules" / "orphan_user" / "main.nf",
            MODULE_MAIN_NF.replace("@citation fastp", "@citation orphan_tool"),
        )
        report = validate_citations(repo)
        assert report["summary"]["orphans_total"] == 0
        assert report["summary"]["missing_total"] == 0
        assert report["summary"]["expected_orphans_total"] == 1

    def test_missing_citations_yml_returns_empty_keys(self, tmp_path: Path):
        # Absent citations.yml should not raise — callers treat an empty set
        # the same way the lint runner does.
        (tmp_path / "modules").mkdir()
        report = validate_citations(tmp_path)
        assert report["summary"]["yml_total"] == 0

    def test_component_without_groovydoc_ignored(self, repo):
        _write(repo / "modules" / "nodoc" / "main.nf", "process NODOC { }\n")
        # Should not crash and should not inflate referenced set.
        report = validate_citations(repo)
        assert "nodoc" not in {
            item["component"] for item in report["missing_workflow_keys"]
        }


class TestPotentialHomes:
    """Coverage for the potential_homes heuristics that suggest orphan wire-ups."""

    def test_directory_match(self, repo):
        # An `orphan_tool/` directory under modules should flag as a candidate.
        _write(repo / "modules" / "orphan_tool" / "main.nf", "process X { }\n")
        report = validate_citations(repo)
        homes = report["potential_homes"].get("orphan_tool", [])
        assert any(h["type"] == "directory" for h in homes), homes

    def test_toolname_match(self, repo):
        # A `bioconda::orphan_tool` toolName in a module.config should flag.
        _write(
            repo / "modules" / "other" / "module.config",
            "process {\n    withName: 'OTHER' {\n"
            '        ext.toolName = "bioconda::orphan_tool=1.0"\n    }\n}\n',
        )
        _write(repo / "modules" / "other" / "main.nf", "process OTHER { }\n")
        report = validate_citations(repo)
        homes = report["potential_homes"].get("orphan_tool", [])
        assert any(h["type"] == "toolName" for h in homes), homes

    def test_config_param_match(self, repo):
        # A non-toolName config line that mentions the key should flag as config_param.
        _write(
            repo / "modules" / "other" / "module.config",
            "params {\n    some_aligner = 'orphan_tool'\n}\n",
        )
        _write(repo / "modules" / "other" / "main.nf", "process OTHER { }\n")
        report = validate_citations(repo)
        homes = report["potential_homes"].get("orphan_tool", [])
        assert any(h["type"] == "config_param" for h in homes), homes

    def test_script_token_match(self, repo):
        # A script block that invokes the orphan as a shell token should flag.
        nf = (
            "/**\n * user\n * @citation fastp\n */\n"
            'process USER {\n    script:\n        """\n        orphan_tool --help\n        """\n}\n'
        )
        _write(repo / "modules" / "user" / "main.nf", nf)
        report = validate_citations(repo)
        homes = report["potential_homes"].get("orphan_tool", [])
        assert any(h["type"] == "script_token" for h in homes), homes

    def test_sibling_key_match(self, repo):
        # `orphan_tool` in the baseline yml has no sibling. Add `orphan_tool2`
        # and confirm the heuristic flags the referenced `orphan_tool` as its
        # likely canonical twin.
        yml = (repo / "data" / "citations.yml").read_text()
        yml += "  orphan_tool2:\n    name: Orphan 2\n    cite: |\n      placeholder.\n"
        (repo / "data" / "citations.yml").write_text(yml)
        _write(
            repo / "modules" / "orphan_user" / "main.nf",
            MODULE_MAIN_NF.replace("@citation fastp", "@citation orphan_tool"),
        )
        report = validate_citations(repo)
        homes = report["potential_homes"].get("orphan_tool2", [])
        assert any(
            h["type"] == "sibling_key" and "orphan_tool" in h["path"] for h in homes
        ), homes

    def test_expected_orphans_get_no_homes(self, repo):
        # Provenance-only entries should not be passed to the heuristic engine.
        report = validate_citations(repo)
        assert "nextflow" not in report["potential_homes"]


class TestCitationsCliValidate:
    """CLI-level coverage for `bactopia-citations --validate`."""

    def test_json_clean_exits_zero(self, repo):
        _write(
            repo / "modules" / "orphan_user" / "main.nf",
            MODULE_MAIN_NF.replace("@citation fastp", "@citation orphan_tool"),
        )
        runner = CliRunner()
        result = runner.invoke(
            citations_cmd,
            ["--bactopia-path", str(repo), "--validate", "--json"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["summary"]["orphans_total"] == 0
        assert payload["summary"]["missing_total"] == 0
        # Provenance-only entries surface in the JSON but don't fail the run.
        assert payload["summary"]["expected_orphans_total"] == 1

    def test_json_expected_orphans_alone_exits_zero(self, repo):
        # Only the provenance-only nextflow entry + the orphan_tool reference
        # added here. Real orphans go to zero; expected_orphans = 1; exit 0.
        _write(
            repo / "modules" / "orphan_user" / "main.nf",
            MODULE_MAIN_NF.replace("@citation fastp", "@citation orphan_tool"),
        )
        runner = CliRunner()
        result = runner.invoke(
            citations_cmd,
            ["--bactopia-path", str(repo), "--validate", "--json"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["expected_orphans"]["tools"] == ["nextflow"]

    def test_json_issues_exit_nonzero(self, repo):
        _write(repo / "workflows" / "rogue" / "main.nf", WORKFLOW_MAIN_NF_BAD)
        runner = CliRunner()
        result = runner.invoke(
            citations_cmd,
            ["--bactopia-path", str(repo), "--validate", "--json"],
        )
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["summary"]["missing_total"] > 0

    def test_missing_repo_is_user_error(self, tmp_path: Path):
        runner = CliRunner()
        result = runner.invoke(
            citations_cmd,
            ["--bactopia-path", str(tmp_path), "--validate", "--json"],
        )
        # Bad --bactopia-path should exit non-zero via ClickException rather
        # than raising an unhandled error. rich-click wraps the message in a
        # formatted banner so checking exit code is the stable assertion.
        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit)
