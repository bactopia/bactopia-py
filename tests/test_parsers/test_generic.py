"""Tests for bactopia.parsers.generic."""

import pytest

from bactopia.parsers.generic import parse_json, parse_table, parse_yaml, read_vcf


class TestParseTable:
    def test_with_header(self, parser_fixtures):
        result = parse_table(str(parser_fixtures / "sample.tsv"))
        assert len(result) == 2
        assert result[0]["col1"] == "a"
        assert result[1]["col2"] == "e"

    def test_without_header(self, parser_fixtures):
        result = parse_table(
            str(parser_fixtures / "sample_no_header.tsv"), has_header=False
        )
        assert len(result) == 2
        assert result[0] == ["a", "b", "c"]

    def test_csv_delimiter(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b,c\n1,2,3\n")
        result = parse_table(str(csv_file), delimiter=",")
        assert result[0]["a"] == "1"


class TestParseJson:
    def test_basic(self, parser_fixtures):
        result = parse_json(str(parser_fixtures / "sample.json"))
        assert result == {"key1": "value1", "key2": 42}


class TestParseYaml:
    def test_basic(self, parser_fixtures):
        result = parse_yaml(str(parser_fixtures / "sample.yaml"))
        assert result == {"key1": "value1", "key2": 42}


class TestReadVcf:
    def test_basic(self, parser_fixtures):
        result = read_vcf(str(parser_fixtures / "sample.vcf"))
        assert "chr1" in result
        assert "100" in result["chr1"]
        assert "200" in result["chr1"]

    def test_empty_vcf(self, tmp_path):
        vcf = tmp_path / "empty.vcf"
        vcf.write_text("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\n")
        result = read_vcf(str(vcf))
        assert result == {}


class TestReadFasta:
    def test_basic(self, parser_fixtures):
        from bactopia.parsers.generic import read_fasta

        result = read_fasta(str(parser_fixtures / "sample.fasta"))
        assert "seq1" in result
        assert result["seq1"] == "ATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCG"
