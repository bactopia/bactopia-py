"""Functional tests for teton_prepare and check_assembly_accession pipeline scripts."""

from pathlib import Path

from click.testing import CliRunner

from bactopia.cli.pipeline.check_assembly_accession import check_assembly_accession
from bactopia.cli.pipeline.teton_prepare import teton_prepare


class TestTetonPrepare:
    def _create_fastqs(self, tmp_path, prefix, filenames):
        """Create empty FASTQ files at the expected scrubber output path."""
        scrubber_dir = tmp_path / "results" / prefix / "teton" / "tools" / "scrubber"
        scrubber_dir.mkdir(parents=True, exist_ok=True)
        for fname in filenames:
            (scrubber_dir / fname).write_text("")

    def test_bacteria_paired_end(self, tmp_path, pipeline_fixtures, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._create_fastqs(tmp_path, "sample1", ["R1.fastq.gz", "R2.fastq.gz"])
        outdir = str(tmp_path / "results")

        runner = CliRunner()
        result = runner.invoke(
            teton_prepare,
            [
                "sample1",
                str(pipeline_fixtures / "sizemeup_bacteria.tsv"),
                "paired-end",
                "R1.fastq.gz,R2.fastq.gz",
                outdir,
            ],
        )
        assert result.exit_code == 0

        bacteria = (tmp_path / "sample1.bacteria.tsv").read_text().strip().split("\n")
        nonbacteria = (
            (tmp_path / "sample1.nonbacteria.tsv").read_text().strip().split("\n")
        )
        # Bacteria file should have header + data row
        assert len(bacteria) == 2
        assert "2800000" in bacteria[1]
        assert "Staphylococcus aureus" in bacteria[1]
        # Nonbacteria file should have header only
        assert len(nonbacteria) == 1

    def test_nonbacteria(self, tmp_path, pipeline_fixtures, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._create_fastqs(tmp_path, "sample1", ["R1.fastq.gz", "R2.fastq.gz"])
        outdir = str(tmp_path / "results")

        runner = CliRunner()
        result = runner.invoke(
            teton_prepare,
            [
                "sample1",
                str(pipeline_fixtures / "sizemeup_nonbacteria.tsv"),
                "paired-end",
                "R1.fastq.gz,R2.fastq.gz",
                outdir,
            ],
        )
        assert result.exit_code == 0

        bacteria = (tmp_path / "sample1.bacteria.tsv").read_text().strip().split("\n")
        nonbacteria = (
            (tmp_path / "sample1.nonbacteria.tsv").read_text().strip().split("\n")
        )
        # Bacteria should be header only, nonbacteria should have data
        assert len(bacteria) == 1
        assert len(nonbacteria) == 2
        assert "Saccharomyces cerevisiae" in nonbacteria[1]

    def test_single_end(self, tmp_path, pipeline_fixtures, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._create_fastqs(tmp_path, "sample1", ["R1.fastq.gz"])
        outdir = str(tmp_path / "results")

        runner = CliRunner()
        result = runner.invoke(
            teton_prepare,
            [
                "sample1",
                str(pipeline_fixtures / "sizemeup_bacteria.tsv"),
                "single-end",
                "R1.fastq.gz",
                outdir,
            ],
        )
        assert result.exit_code == 0

        lines = (tmp_path / "sample1.bacteria.tsv").read_text().split("\n")
        header_cols = lines[0].strip().split("\t")
        data_cols = lines[1].split("\t")
        r2_idx = header_cols.index("r2")
        extra_idx = header_cols.index("extra")
        r2_val = data_cols[r2_idx] if r2_idx < len(data_cols) else ""
        extra_val = data_cols[extra_idx] if extra_idx < len(data_cols) else ""
        assert r2_val.strip() == ""
        assert extra_val.strip() == ""

    def test_cloud_path_skips_validation(
        self, tmp_path, pipeline_fixtures, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            teton_prepare,
            [
                "sample1",
                str(pipeline_fixtures / "sizemeup_bacteria.tsv"),
                "paired-end",
                "R1.fastq.gz,R2.fastq.gz",
                "s3://bucket/results",
            ],
        )
        assert result.exit_code == 0

    def test_missing_local_fastq_exits(self, tmp_path, pipeline_fixtures, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Don't create any FASTQ files -- should fail
        runner = CliRunner()
        result = runner.invoke(
            teton_prepare,
            [
                "sample1",
                str(pipeline_fixtures / "sizemeup_bacteria.tsv"),
                "paired-end",
                "R1.fastq.gz,R2.fastq.gz",
                str(tmp_path / "results"),
            ],
        )
        assert result.exit_code != 0


class TestCheckAssemblyAccession:
    def test_current_accession(self, mocker):
        mocker.patch(
            "bactopia.cli.pipeline.check_assembly_accession.check_assembly_version",
            return_value=["GCF_000009045.2", False],
        )
        runner = CliRunner()
        result = runner.invoke(check_assembly_accession, ["GCF_000009045.1"])
        assert result.exit_code == 0
        assert "GCF_000009045.2" in result.output

    def test_excluded_accession(self, mocker):
        mocker.patch(
            "bactopia.cli.pipeline.check_assembly_accession.check_assembly_version",
            return_value=["derived from metagenome", True],
        )
        runner = CliRunner()
        result = runner.invoke(check_assembly_accession, ["GCF_000009045.1"])
        assert result.exit_code == 0
        # Excluded accession shows skip message but no bare accession line
        assert "Skipping" in result.output
        # Should not contain a standalone accession (the non-excluded path prints one)
        lines = [
            line
            for line in result.output.strip().split("\n")
            if not line.startswith("Skipping")
        ]
        assert all(line.strip() == "" for line in lines)
