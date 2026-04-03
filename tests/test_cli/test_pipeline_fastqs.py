"""Functional tests for check_fastqs and scrubber_summary pipeline scripts."""

import os

from click.testing import CliRunner

from bactopia.cli.pipeline.check_fastqs import check_fastqs
from bactopia.cli.pipeline.scrubber_summary import scrubber_summary


class TestCheckFastqsPairedEnd:
    def test_passes_when_above_thresholds(
        self, tmp_path, pipeline_fixtures, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            check_fastqs,
            [
                "--sample",
                "test",
                "--fq1",
                str(pipeline_fixtures / "fq_r1.json"),
                "--fq2",
                str(pipeline_fixtures / "fq_r2.json"),
                "--min_reads",
                "100",
                "--min_basepairs",
                "1000",
            ],
        )
        assert result.exit_code == 0
        # No error files should be created
        error_files = [f for f in os.listdir(tmp_path) if f.endswith("-error.txt")]
        assert error_files == []


class TestCheckFastqsSingleEnd:
    def test_se_passes(self, tmp_path, pipeline_fixtures, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            check_fastqs,
            [
                "--sample",
                "test",
                "--fq1",
                str(pipeline_fixtures / "fq_r1.json"),
                "--min_reads",
                "100",
                "--min_basepairs",
                "1000",
            ],
        )
        assert result.exit_code == 0
        error_files = [f for f in os.listdir(tmp_path) if f.endswith("-error.txt")]
        assert error_files == []

    def test_ont_skips_read_check(self, tmp_path, pipeline_fixtures, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            check_fastqs,
            [
                "--sample",
                "test",
                "--fq1",
                str(pipeline_fixtures / "fq_low.json"),
                "--runtype",
                "ont",
                "--min_reads",
                "999999",
                "--min_basepairs",
                "0",
            ],
        )
        assert result.exit_code == 0
        # ONT skips read count check, so no low-read-count error
        assert not (tmp_path / "test-low-read-count-error.txt").exists()


class TestCheckFastqsErrors:
    def test_low_read_count(self, tmp_path, pipeline_fixtures, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            check_fastqs,
            [
                "--sample",
                "test",
                "--fq1",
                str(pipeline_fixtures / "fq_low.json"),
                "--min_reads",
                "1000",
                "--min_basepairs",
                "0",
            ],
        )
        assert result.exit_code == 0
        assert (tmp_path / "test-low-read-count-error.txt").exists()

    def test_different_read_counts(self, tmp_path, pipeline_fixtures, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            check_fastqs,
            [
                "--sample",
                "test",
                "--fq1",
                str(pipeline_fixtures / "fq_r1.json"),
                "--fq2",
                str(pipeline_fixtures / "fq_r2_unequal_reads.json"),
                "--min_reads",
                "0",
                "--min_basepairs",
                "0",
            ],
        )
        assert result.exit_code == 0
        assert (tmp_path / "test-different-read-count-error.txt").exists()

    def test_low_basepairs(self, tmp_path, pipeline_fixtures, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            check_fastqs,
            [
                "--sample",
                "test",
                "--fq1",
                str(pipeline_fixtures / "fq_low.json"),
                "--min_reads",
                "0",
                "--min_basepairs",
                "999999",
            ],
        )
        assert result.exit_code == 0
        assert (tmp_path / "test-low-sequence-depth-error.txt").exists()

    def test_low_proportion(self, tmp_path, pipeline_fixtures, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            check_fastqs,
            [
                "--sample",
                "test",
                "--fq1",
                str(pipeline_fixtures / "fq_r1.json"),
                "--fq2",
                str(pipeline_fixtures / "fq_r2_low_bp.json"),
                "--min_reads",
                "0",
                "--min_basepairs",
                "0",
                "--min_proportion",
                "0.9",
            ],
        )
        assert result.exit_code == 0
        assert (tmp_path / "test-low-basepair-proportion-error.txt").exists()


class TestScrubberSummary:
    def test_happy_path(self, pipeline_fixtures):
        runner = CliRunner()
        result = runner.invoke(
            scrubber_summary,
            [
                "test",
                str(pipeline_fixtures / "fq_r1.json"),
                str(pipeline_fixtures / "fq_scrubbed.json"),
            ],
        )
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert len(lines) == 2
        assert (
            lines[0]
            == "sample\toriginal_read_total\tscrubbed_read_total\thost_read_total"
        )
        assert lines[1] == "test\t50000\t45000\t5000"
