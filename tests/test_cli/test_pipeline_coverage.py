"""Functional tests for cleanup_coverage and mask_consensus pipeline scripts."""

from click.testing import CliRunner

from bactopia.cli.pipeline.cleanup_coverage import cleanup_coverage
from bactopia.cli.pipeline.mask_consensus import mask_consensus


class TestCleanupCoverage:
    def test_reformats_tabbed_input(self, parser_fixtures):
        runner = CliRunner()
        result = runner.invoke(
            cleanup_coverage,
            [str(parser_fixtures / "coverage_tabbed.txt")],
        )
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert lines[0] == "##contig=<ID=chr1,length=3>"
        assert lines[1:] == ["10", "20", "15"]

    def test_multi_contig(self, tmp_path):
        cov_file = tmp_path / "multi.txt"
        cov_file.write_text(
            "##contig=<ID=chr1,length=2>\n"
            "chr1\t1\t10\n"
            "chr1\t2\t20\n"
            "##contig=<ID=chr2,length=3>\n"
            "chr2\t1\t5\n"
            "chr2\t2\t15\n"
            "chr2\t3\t25\n"
        )
        runner = CliRunner()
        result = runner.invoke(cleanup_coverage, [str(cov_file)])
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert "##contig=<ID=chr1,length=2>" in lines
        assert "##contig=<ID=chr2,length=3>" in lines
        assert lines.count("##contig=<ID=chr1,length=2>") == 1
        assert lines.count("##contig=<ID=chr2,length=3>") == 1


class TestMaskConsensus:
    def test_masking_logic(self, pipeline_fixtures):
        """Test masking with coverage thresholds and substitution positions.

        Fixture data (10 bases, mincov=10):
          pos  base  cov  sub?  expected
          1    A     15   no    A (uppercase, cov >= mincov)
          2    C     20   yes   c (lowercase, sub at pos 2)
          3    G     0    no    n (no coverage)
          4    T     5    no    N (low coverage, 0 < cov < mincov)
          5    A     30   yes   a (lowercase, sub at pos 5)
          6    C     10   no    C (uppercase, cov == mincov)
          7    G     0    no    n (no coverage)
          8    T     25   no    T (uppercase)
          9    A     8    no    N (low coverage)
          10   C     12   no    C (uppercase)
        """
        runner = CliRunner()
        result = runner.invoke(
            mask_consensus,
            [
                "sample1",
                "GCF_000001",
                str(pipeline_fixtures / "mask_ref.fasta"),
                str(pipeline_fixtures / "mask_subs.vcf"),
                str(pipeline_fixtures / "mask_coverage.txt"),
                "--mincov", "10",
            ],
        )
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        # First line is header
        assert lines[0].startswith(">gnl|chr1|sample1")
        assert "assembly_accession=GCF_000001" in lines[0]
        # Sequence is on remaining lines (may wrap at 60bp, but 10bp fits in one)
        seq = "".join(lines[1:])
        assert seq == "AcnNaCnTNC"

    def test_no_substitutions(self, tmp_path, pipeline_fixtures):
        empty_vcf = tmp_path / "empty.vcf"
        empty_vcf.write_text(
            "##fileformat=VCFv4.2\n"
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        )
        runner = CliRunner()
        result = runner.invoke(
            mask_consensus,
            [
                "sample1",
                "GCF_000001",
                str(pipeline_fixtures / "mask_ref.fasta"),
                str(empty_vcf),
                str(pipeline_fixtures / "mask_coverage.txt"),
                "--mincov", "10",
            ],
        )
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        seq = "".join(lines[1:])
        # No subs: all uppercase or N/n, no lowercase
        assert seq == seq.upper() or "n" in seq
        # Specifically: no lowercase letters except 'n'
        for ch in seq:
            if ch.islower():
                assert ch == "n"
