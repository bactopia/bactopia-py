"""Tests for bactopia.lint.docs.validate_docs."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from bactopia.cli.docs import docs as docs_cmd
from bactopia.lint.docs import validate_docs

PATTERNS_YML = """\
patterns:
  - id: D001
    pattern: flattenPaths
    literal: true
    severity: FAIL
    hint: Function removed; remove or rephrase.
  - id: D002
    pattern: '4[- ]channel'
    severity: FAIL
    hint: Subworkflows emit 2 channels (sample_outputs/run_outputs).
  - id: D004
    pattern: '\\bmeta:\\s*Map\\b'
    severity: FAIL
    hint: meta is now a Record, not a Map.
"""

PYPROJECT = """\
[tool.poetry.scripts]
bactopia-status = "bactopia.cli.status:main"
bactopia-test = "bactopia.cli.testing:main"
bactopia-lint = "bactopia.cli.lint:main"

[tool.poetry.dependencies]
python = "^3.10.0"
"""

MODULE_RULE_PY = """\
def rule_M001():
    rid = "M001"
    return rid

def rule_M035():
    rid = "M035"
    return rid
"""

WORKFLOW_RULE_PY = """\
def rule_W001():
    rid = "W001"
    return rid
"""

NEXTFLOW_CONFIG = """\
manifest {
    name = "bactopia"
    nextflowVersion = '>=25.04.6'
}
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Build a minimal Bactopia-like repo + sibling bactopia-py."""
    bactopia = tmp_path / "bactopia"
    bactopia_py = tmp_path / "bactopia-py"

    _write(bactopia / "data" / "docs-patterns.yml", PATTERNS_YML)
    _write(bactopia / "nextflow.config", NEXTFLOW_CONFIG)

    # Two modules + one subworkflow + one workflow + root main.nf for
    # workflow count = 1 (workflows/foo) + 1 (root) = 2.
    _write(bactopia / "modules" / "fastp" / "main.nf", "process FASTP {}\n")
    _write(bactopia / "modules" / "spades" / "main.nf", "process SPADES {}\n")
    _write(bactopia / "subworkflows" / "qc" / "main.nf", "workflow QC {}\n")
    _write(bactopia / "workflows" / "test_tool" / "main.nf", "workflow TEST {}\n")
    _write(bactopia / "main.nf", "workflow BACTOPIA {}\n")

    # Sibling bactopia-py with pyproject.toml + a couple of lint rule files.
    _write(bactopia_py / "pyproject.toml", PYPROJECT)
    _write(
        bactopia_py / "bactopia" / "lint" / "rules" / "module_rules.py", MODULE_RULE_PY
    )
    _write(
        bactopia_py / "bactopia" / "lint" / "rules" / "workflow_rules.py",
        WORKFLOW_RULE_PY,
    )

    # Empty docs dir; tests add files as needed.
    (bactopia / ".claude" / "docs").mkdir(parents=True)
    return bactopia


def _add_doc(repo: Path, rel: str, content: str) -> None:
    _write(repo / ".claude" / "docs" / rel, content)


class TestValidateDocsShape:
    def test_returns_expected_keys(self, repo):
        report = validate_docs(repo, skip_path_check=True)
        assert set(report.keys()) >= {
            "bactopia_path",
            "docs_path",
            "patterns_file",
            "ground_truth",
            "files_scanned",
            "deprecated_patterns",
            "ground_truth_violations",
            "summary",
        }
        assert set(report["summary"].keys()) >= {
            "files_scanned",
            "deprecated_pattern_hits",
            "ground_truth_violations",
            "fail",
            "warn",
            "patterns_loaded",
        }

    def test_empty_docs_dir_is_clean(self, repo):
        report = validate_docs(repo, skip_path_check=True)
        assert report["summary"]["files_scanned"] == 0
        assert report["summary"]["fail"] == 0
        # Patterns still load even when no docs were scanned.
        assert report["summary"]["patterns_loaded"] == 3

    def test_ground_truth_counts(self, repo):
        report = validate_docs(repo, skip_path_check=True)
        counts = report["ground_truth"]["counts"]
        assert counts == {"modules": 2, "subworkflows": 1, "workflows": 2}
        assert report["ground_truth"]["nextflow_version"] == "25.04.6"
        assert report["ground_truth"]["cli_commands_total"] == 3
        assert report["ground_truth"]["lint_rule_ids_total"] == 3


class TestDeprecatedPatterns:
    def test_d001_flattenpaths_literal(self, repo):
        _add_doc(repo, "ref.md", "Use flattenPaths for aggregate outputs.\n")
        report = validate_docs(repo, skip_path_check=True)
        hits = report["deprecated_patterns"]
        assert len(hits) == 1
        assert hits[0]["rule_id"] == "D001"
        assert hits[0]["line"] == 1
        assert "flattenPaths" in hits[0]["match"]

    def test_d002_4channel_regex(self, repo):
        _add_doc(repo, "ref.md", "Verify all 4-channel emission.\n")
        report = validate_docs(repo, skip_path_check=True)
        d002 = [h for h in report["deprecated_patterns"] if h["rule_id"] == "D002"]
        assert len(d002) == 1

    def test_d004_meta_map_word_boundary(self, repo):
        _add_doc(
            repo, "ref.md", "- meta: Map containing sample info\nmeta: Record OK\n"
        )
        report = validate_docs(repo, skip_path_check=True)
        d004 = [h for h in report["deprecated_patterns"] if h["rule_id"] == "D004"]
        assert len(d004) == 1
        assert d004[0]["line"] == 1

    def test_inline_ignore_suppresses(self, repo):
        _add_doc(
            repo,
            "ref.md",
            "Use flattenPaths in old code. <!-- bactopia-docs: ignore D001 -->\n",
        )
        report = validate_docs(repo, skip_path_check=True)
        assert all(h["rule_id"] != "D001" for h in report["deprecated_patterns"])

    def test_inline_ignore_multiple_rules(self, repo):
        _add_doc(
            repo,
            "ref.md",
            "Use flattenPaths and 4-channel. <!-- bactopia-docs: ignore D001, D002 -->\n",
        )
        report = validate_docs(repo, skip_path_check=True)
        assert report["deprecated_patterns"] == []


class TestCountClaims:
    def test_d101_module_count_mismatch(self, repo):
        _add_doc(repo, "ref.md", "Bactopia ships 96 modules currently.\n")
        report = validate_docs(repo, skip_path_check=True)
        d101 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D101"]
        assert len(d101) == 1
        assert d101[0]["claim"] == "96 modules"
        assert d101[0]["actual"] == "2 modules"  # fixture has 2 modules

    def test_d102_subworkflow_count_match(self, repo):
        _add_doc(repo, "ref.md", "There is 1 subworkflow.\n")
        report = validate_docs(repo, skip_path_check=True)
        d102 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D102"]
        assert d102 == []

    def test_d103_workflow_count_mismatch(self, repo):
        # Fixture: 2 workflows (1 under workflows/ + 1 root main.nf).
        _add_doc(repo, "ref.md", "Total 70 workflows across all tiers.\n")
        report = validate_docs(repo, skip_path_check=True)
        d103 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D103"]
        assert len(d103) == 1

    def test_count_ignores_heading_numbers(self, repo):
        # "1.1 Module Structure" must not match as "1 module"; "1:1 module
        # wrapper" must not match either. Both are common in section headers
        # and ratio descriptions.
        _add_doc(
            repo,
            "ref.md",
            "### 1.1 Module Structure\n"
            "1:1 module wrapper pattern\n"
            "### 6.3 Workflow-Dependent Behavior\n",
        )
        report = validate_docs(repo, skip_path_check=True)
        count_hits = [
            h
            for h in report["ground_truth_violations"]
            if h["rule_id"] in ("D101", "D102", "D103")
        ]
        assert count_hits == []


class TestVersionClaims:
    def test_d104_mismatch(self, repo):
        _add_doc(repo, "ref.md", "Bactopia uses Nextflow 26.01.0.\n")
        report = validate_docs(repo, skip_path_check=True)
        d104 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D104"]
        assert len(d104) == 1
        assert d104[0]["claim"] == "Nextflow 26.01.0"
        assert d104[0]["actual"] == "Nextflow 25.04.6"

    def test_d104_match(self, repo):
        _add_doc(repo, "ref.md", "Requires Nextflow 25.04.6 or later.\n")
        report = validate_docs(repo, skip_path_check=True)
        d104 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D104"]
        assert d104 == []

    def test_d104_major_minor_match_allowed(self, repo):
        _add_doc(repo, "ref.md", "Requires Nextflow 25.04 or later.\n")
        report = validate_docs(repo, skip_path_check=True)
        d104 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D104"]
        assert d104 == []

    def test_d104_skips_plus_suffix(self, repo):
        _add_doc(repo, "ref.md", "Native Path? supported in Nextflow 26.04+ syntax.\n")
        report = validate_docs(repo, skip_path_check=True)
        d104 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D104"]
        assert d104 == []

    def test_d104_skips_x_range(self, repo):
        _add_doc(
            repo, "ref.md", "Verify Nextflow version meets requirements (v25.10.x+).\n"
        )
        report = validate_docs(repo, skip_path_check=True)
        d104 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D104"]
        assert d104 == []

    def test_d104_skips_until_keyword(self, repo):
        _add_doc(
            repo, "ref.md", "Required until Nextflow v26.04 stabilizes the feature.\n"
        )
        report = validate_docs(repo, skip_path_check=True)
        d104 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D104"]
        assert d104 == []


class TestCliReferences:
    def test_d105_unknown_command(self, repo):
        _add_doc(repo, "ref.md", "Run `bactopia-nonexistent` to see options.\n")
        report = validate_docs(repo, skip_path_check=True)
        d105 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D105"]
        assert len(d105) == 1
        assert d105[0]["reference"] == "bactopia-nonexistent"

    def test_d105_known_command_clean(self, repo):
        _add_doc(repo, "ref.md", "Run `bactopia-status` to see repo state.\n")
        report = validate_docs(repo, skip_path_check=True)
        d105 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D105"]
        assert d105 == []

    def test_d105_ignores_prose_mentions(self, repo):
        _add_doc(
            repo,
            "ref.md",
            "The bactopia-tools directory and bactopia-py companion repo are noted.\n",
        )
        report = validate_docs(repo, skip_path_check=True)
        d105 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D105"]
        assert d105 == []

    def test_d105_skipped_when_bactopia_py_missing(self, tmp_path):
        repo = tmp_path / "bactopia"
        _write(repo / "data" / "docs-patterns.yml", PATTERNS_YML)
        _write(repo / "nextflow.config", NEXTFLOW_CONFIG)
        _write(repo / "modules" / "fastp" / "main.nf", "")
        _add_doc(repo, "ref.md", "Run `bactopia-anything`.\n")
        report = validate_docs(repo, skip_path_check=True)
        d105 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D105"]
        assert d105 == []
        assert report["ground_truth"]["bactopia_py_resolved"] is None


class TestRuleIdReferences:
    def test_d106_unknown_rule(self, repo):
        _add_doc(repo, "ref.md", "Lint rule M999 catches this issue.\n")
        report = validate_docs(repo, skip_path_check=True)
        d106 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D106"]
        assert len(d106) == 1
        assert d106[0]["reference"] == "M999"

    def test_d106_known_rule_clean(self, repo):
        _add_doc(repo, "ref.md", "Rules M001, M035, and W001 are enforced.\n")
        report = validate_docs(repo, skip_path_check=True)
        d106 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D106"]
        assert d106 == []


class TestPathReferences:
    def test_d108_broken_link_target(self, repo):
        _add_doc(repo, "ref.md", "See [the missing doc](nonexistent/file.md).\n")
        report = validate_docs(repo)
        d108 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D108"]
        assert len(d108) == 1
        assert d108[0]["reference"] == "nonexistent/file.md"

    def test_d108_valid_link_clean(self, repo):
        _add_doc(repo, "ref.md", "See [config](../../nextflow.config).\n")
        report = validate_docs(repo)
        d108 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D108"]
        assert d108 == []

    def test_d108_skips_external_urls(self, repo):
        _add_doc(repo, "ref.md", "See [docs](https://bactopia.github.io/) for more.\n")
        report = validate_docs(repo)
        d108 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D108"]
        assert d108 == []

    def test_d108_skips_placeholder_targets(self, repo):
        _add_doc(
            repo,
            "ref.md",
            "Use [Markdown links](url).\nInclude [ToolName](URL) links.\n",
        )
        report = validate_docs(repo)
        d108 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D108"]
        assert d108 == []

    def test_d108_skipped_with_flag(self, repo):
        _add_doc(repo, "ref.md", "See [missing](nonexistent.md).\n")
        report = validate_docs(repo, skip_path_check=True)
        d108 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D108"]
        assert d108 == []


def _add_skill(repo: Path, name: str, description: str) -> None:
    """Write a minimal SKILL.md under .claude/skills/<name>/."""
    frontmatter = f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n"
    _write(repo / ".claude" / "skills" / name / "SKILL.md", frontmatter)


def _skills_doc(rows: list[tuple[str, str, str]]) -> str:
    """Render a minimal 06-skills.md containing a table with the given rows.

    Each row is (name, backend, purpose). Backend ``"—"`` renders as em-dash.
    """
    header = "# Skills Reference\n\n## Project-local skills\n\n"
    header += "| Skill | Backend | Purpose |\n|---|---|---|\n"
    body = "\n".join(
        f"| [{name}](../../skills/{name}/) | {backend} | {purpose} |"
        for name, backend, purpose in rows
    )
    return header + body + "\n"


class TestSkillInventory:
    def test_d107_clean_happy_path(self, repo):
        _add_skill(repo, "foo", "Do foo things. Extra detail.")
        _add_skill(repo, "bar", "Do bar things. Extra detail.")
        _add_doc(
            repo,
            "reference/06-skills.md",
            _skills_doc(
                [
                    ("bar", "`bactopia-bar`", "Do bar things."),
                    ("foo", "—", "Do foo things."),
                ]
            ),
        )
        report = validate_docs(repo, skip_path_check=True)
        d107 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D107"]
        assert d107 == []
        assert report["ground_truth"]["skills_count"] == 2

    def test_d107_skill_missing_from_doc(self, repo):
        _add_skill(repo, "foo", "Do foo things.")
        _add_skill(repo, "bar", "Do bar things.")
        _add_doc(
            repo,
            "reference/06-skills.md",
            _skills_doc([("foo", "—", "Do foo things.")]),
        )
        report = validate_docs(repo, skip_path_check=True)
        d107 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D107"]
        assert len(d107) == 1
        assert d107[0]["reference"] == "bar"
        assert "not listed" in d107[0]["hint"]

    def test_d107_ghost_skill_in_doc(self, repo):
        _add_skill(repo, "foo", "Do foo things.")
        _add_doc(
            repo,
            "reference/06-skills.md",
            _skills_doc(
                [
                    ("foo", "—", "Do foo things."),
                    ("ghost", "—", "Does nothing."),
                ]
            ),
        )
        report = validate_docs(repo, skip_path_check=True)
        d107 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D107"]
        assert len(d107) == 1
        assert d107[0]["reference"] == "ghost"
        assert "no .claude/skills/ghost" in d107[0]["hint"]

    def test_d107_description_drift(self, repo):
        _add_skill(repo, "foo", "Do foo things with tool X. Extra detail.")
        _add_doc(
            repo,
            "reference/06-skills.md",
            _skills_doc([("foo", "—", "Do bar things with tool Y.")]),
        )
        report = validate_docs(repo, skip_path_check=True)
        d107 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D107"]
        assert len(d107) == 1
        assert d107[0]["reference"] == "foo"
        assert d107[0]["claim"] == "Do bar things with tool Y."
        assert d107[0]["actual"] == "Do foo things with tool X."

    def test_d107_whitespace_case_insensitive_match(self, repo):
        _add_skill(repo, "foo", "Do foo things.  Extra.")
        _add_doc(
            repo,
            "reference/06-skills.md",
            # Extra whitespace and mixed case should still match.
            _skills_doc([("foo", "—", "do  Foo  things.")]),
        )
        report = validate_docs(repo, skip_path_check=True)
        d107 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D107"]
        assert d107 == []

    def test_d107_duplicate_row(self, repo):
        _add_skill(repo, "foo", "Do foo things.")
        _add_doc(
            repo,
            "reference/06-skills.md",
            _skills_doc(
                [
                    ("foo", "—", "Do foo things."),
                    ("foo", "—", "Do foo things."),
                ]
            ),
        )
        report = validate_docs(repo, skip_path_check=True)
        d107 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D107"]
        assert len(d107) == 1
        assert "more than once" in d107[0]["hint"]

    def test_d107_skipped_when_doc_missing(self, repo):
        _add_skill(repo, "foo", "Do foo things.")
        report = validate_docs(repo, skip_path_check=True)
        d107 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D107"]
        assert d107 == []
        assert report["ground_truth"]["skills_count"] == 1

    def test_d107_skipped_when_no_skills(self, repo):
        # Doc present, no skills dir — clean skip.
        _add_doc(repo, "reference/06-skills.md", _skills_doc([]))
        report = validate_docs(repo, skip_path_check=True)
        d107 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D107"]
        assert d107 == []
        assert report["ground_truth"]["skills_count"] == 0

    def test_d107_inline_ignore_suppresses(self, repo):
        _add_skill(repo, "foo", "Do foo things.")
        # Ghost row is suppressed; foo row still needs to be present.
        doc = (
            _skills_doc([("foo", "—", "Do foo things.")]).rstrip("\n")
            + "\n| [ghost](../../skills/ghost/) | — | Does nothing. |"
            " <!-- bactopia-docs: ignore D107 -->\n"
        )
        _add_doc(repo, "reference/06-skills.md", doc)
        report = validate_docs(repo, skip_path_check=True)
        d107 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D107"]
        assert d107 == []

    def test_d107_skill_without_frontmatter_still_counted(self, repo):
        # Skill with no frontmatter is included in inventory but not
        # subject to description drift (empty first_sentence).
        _write(
            repo / ".claude" / "skills" / "nofm" / "SKILL.md",
            "# No frontmatter here\n",
        )
        _add_doc(
            repo,
            "reference/06-skills.md",
            _skills_doc([("nofm", "—", "Some purpose.")]),
        )
        report = validate_docs(repo, skip_path_check=True)
        d107 = [h for h in report["ground_truth_violations"] if h["rule_id"] == "D107"]
        assert d107 == []
        assert report["ground_truth"]["skills_count"] == 1


class TestPatternLoaderEdgeCases:
    def test_missing_patterns_file_returns_empty(self, repo):
        (repo / "data" / "docs-patterns.yml").unlink()
        _add_doc(repo, "ref.md", "Use flattenPaths.\n")
        report = validate_docs(repo, skip_path_check=True)
        assert report["summary"]["patterns_loaded"] == 0
        assert report["deprecated_patterns"] == []

    def test_invalid_regex_skipped(self, repo, caplog):
        _write(
            repo / "data" / "docs-patterns.yml",
            "patterns:\n  - id: D999\n    pattern: '['\n  - id: D001\n    pattern: flattenPaths\n    literal: true\n",
        )
        _add_doc(repo, "ref.md", "Use flattenPaths.\n")
        report = validate_docs(repo, skip_path_check=True)
        # Bad regex skipped, good one still fires.
        assert report["summary"]["patterns_loaded"] == 1
        assert any(h["rule_id"] == "D001" for h in report["deprecated_patterns"])

    def test_literal_flag_escapes(self, repo):
        # Without literal: true a "." would match anything; with it, exact dot only.
        _write(
            repo / "data" / "docs-patterns.yml",
            "patterns:\n  - id: D050\n    pattern: 'foo.bar'\n    literal: true\n",
        )
        _add_doc(repo, "ref.md", "fooXbar should not match\nfoo.bar should match\n")
        report = validate_docs(repo, skip_path_check=True)
        d050 = [h for h in report["deprecated_patterns"] if h["rule_id"] == "D050"]
        assert len(d050) == 1
        assert d050[0]["line"] == 2


class TestCli:
    def test_cli_runs_clean(self, repo):
        runner = CliRunner()
        result = runner.invoke(
            docs_cmd,
            ["--bactopia-path", str(repo), "--skip-path-check"],
        )
        assert result.exit_code == 0
        assert "clean" in result.output.lower()

    def test_cli_exit_1_on_fail(self, repo):
        _add_doc(repo, "ref.md", "Use flattenPaths.\n")
        runner = CliRunner()
        result = runner.invoke(
            docs_cmd,
            ["--bactopia-path", str(repo), "--skip-path-check"],
        )
        assert result.exit_code == 1

    def test_cli_json_output(self, repo):
        _add_doc(repo, "ref.md", "Use flattenPaths.\n")
        runner = CliRunner()
        result = runner.invoke(
            docs_cmd,
            ["--bactopia-path", str(repo), "--skip-path-check", "--json"],
        )
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["summary"]["fail"] >= 1
        assert payload["deprecated_patterns"][0]["rule_id"] == "D001"

    def test_cli_silent_suppresses_clean_output(self, repo):
        runner = CliRunner()
        result = runner.invoke(
            docs_cmd,
            ["--bactopia-path", str(repo), "--skip-path-check", "--silent"],
        )
        assert result.exit_code == 0
        assert result.output == ""

    def test_cli_missing_docs_dir_errors(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(docs_cmd, ["--bactopia-path", str(tmp_path)])
        assert result.exit_code != 0
        assert "Docs directory" in result.output or "not a directory" in result.output
