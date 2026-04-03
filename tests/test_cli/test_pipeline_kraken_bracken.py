"""Functional tests for kraken_bracken_summary and bracken_to_excel."""

import pandas as pd
from click.testing import CliRunner

from bactopia.cli.pipeline.bracken_to_excel import bracken_to_excel
from bactopia.cli.pipeline.kraken_bracken_summary import kraken_bracken_summary


class TestKrakenBrackenSummary:
    def test_happy_path(
        self, tmp_path, parser_fixtures, pipeline_fixtures, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            kraken_bracken_summary,
            [
                "testprefix",
                str(parser_fixtures / "kraken2_report.txt"),
                str(parser_fixtures / "bracken_report.txt"),
                str(pipeline_fixtures / "bracken_abundances.tsv"),
            ],
        )
        assert result.exit_code == 0

        # Check bracken summary TSV
        summary = (tmp_path / "testprefix.bracken.tsv").read_text()
        lines = summary.strip().split("\n")
        assert "bracken_primary_species" in lines[0]
        assert "Staphylococcus aureus" in lines[1]

        # Check adjusted abundances (should include unclassified row)
        adj = pd.read_csv(
            tmp_path / "testprefix.bracken.adjusted.abundances.txt", sep="\t"
        )
        assert "sample" in adj.columns
        assert "unclassified" in adj["name"].values

        # Check classification file
        clf = (tmp_path / "testprefix.bracken.classification.txt").read_text()
        assert "classification" in clf

    def test_no_unclassified(
        self, tmp_path, parser_fixtures, pipeline_fixtures, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        # Create a kraken2 report with no U line (100% classified)
        no_u_report = tmp_path / "kraken2_no_u.txt"
        no_u_report.write_text("100.00\t1000\t0\tR\t1\troot\n")
        runner = CliRunner()
        result = runner.invoke(
            kraken_bracken_summary,
            [
                "testprefix",
                str(no_u_report),
                str(parser_fixtures / "bracken_report.txt"),
                str(pipeline_fixtures / "bracken_abundances.tsv"),
            ],
        )
        assert result.exit_code == 0

        # Adjusted abundances should not have unclassified row
        adj = pd.read_csv(
            tmp_path / "testprefix.bracken.adjusted.abundances.txt", sep="\t"
        )
        assert "unclassified" not in adj["name"].values

        # Summary should have empty unclassified abundance
        summary = (tmp_path / "testprefix.bracken.tsv").read_text()
        lines = summary.split("\n")
        header_cols = lines[0].strip().split("\t")
        data_cols = lines[1].split("\t")
        uncl_idx = header_cols.index("bracken_unclassified_abundance")
        # When no unclassified reads, the column may be empty or absent (trailing tab stripped)
        uncl_val = data_cols[uncl_idx] if uncl_idx < len(data_cols) else ""
        assert uncl_val.strip() == ""

    def test_high_secondary_unknown(
        self, tmp_path, parser_fixtures, pipeline_fixtures, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            kraken_bracken_summary,
            [
                "testprefix",
                str(parser_fixtures / "kraken2_report.txt"),
                str(parser_fixtures / "bracken_report.txt"),
                str(pipeline_fixtures / "bracken_abundances.tsv"),
                "--max_secondary_percent",
                "0.001",
            ],
        )
        assert result.exit_code == 0
        clf = (tmp_path / "testprefix.bracken.classification.txt").read_text()
        assert "UNKNOWN_SPECIES" in clf


class TestBrackenToExcel:
    def test_happy_path(self, tmp_path, pipeline_fixtures, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            bracken_to_excel,
            ["testprefix", str(pipeline_fixtures / "bracken_adjusted_abundances.tsv")],
        )
        assert result.exit_code == 0

        xlsx = tmp_path / "testprefix.xlsx"
        assert xlsx.exists()

        sheets = pd.read_excel(xlsx, sheet_name=None)
        assert "sample1" in sheets
        assert "sample2" in sheets
        # Default excludes unclassified
        for name, df in sheets.items():
            assert "unclassified" not in df["name"].values
        # Sorted by fraction descending
        for name, df in sheets.items():
            fracs = list(df["fraction_total_reads"])
            assert fracs == sorted(fracs, reverse=True)

    def test_include_unclassified(self, tmp_path, pipeline_fixtures, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            bracken_to_excel,
            [
                "testprefix",
                str(pipeline_fixtures / "bracken_adjusted_abundances.tsv"),
                "--include_unclassified",
            ],
        )
        assert result.exit_code == 0

        sheets = pd.read_excel(tmp_path / "testprefix.xlsx", sheet_name=None)
        # At least one sheet should have unclassified
        has_unclassified = any(
            "unclassified" in df["name"].values for df in sheets.values()
        )
        assert has_unclassified

    def test_limit(self, tmp_path, pipeline_fixtures, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            bracken_to_excel,
            [
                "testprefix",
                str(pipeline_fixtures / "bracken_adjusted_abundances.tsv"),
                "--limit",
                "1",
            ],
        )
        assert result.exit_code == 0

        sheets = pd.read_excel(tmp_path / "testprefix.xlsx", sheet_name=None)
        for name, df in sheets.items():
            assert len(df) == 1
