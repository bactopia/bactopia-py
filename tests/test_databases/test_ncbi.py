"""Tests for bactopia.databases.ncbi."""

import gzip

import pytest
import responses

from bactopia.databases.ncbi import (
    NCBI_GENOME_SIZE_URL,
    get_ncbi_genome_size,
    get_taxid_from_species,
    is_biosample,
)


class TestIsBiosample:
    def test_samn(self):
        assert is_biosample("SAMN12345678") is True

    def test_same(self):
        assert is_biosample("SAME12345678") is True

    def test_samd(self):
        assert is_biosample("SAMD12345678") is True

    def test_ers(self):
        assert is_biosample("ERS123456") is True

    def test_drs(self):
        assert is_biosample("DRS123456") is True

    def test_srs(self):
        assert is_biosample("SRS123456") is True

    def test_not_biosample(self):
        assert is_biosample("SRR12345678") is False

    def test_prjna(self):
        assert is_biosample("PRJNA12345") is False


class TestGetNcbiGenomeSize:
    @responses.activate
    def test_success(self):
        tsv = "#species_taxid\tspecies_name\texpected_ungapped_length\n1280\tStaphylococcus aureus\t2800000\n"
        compressed = gzip.compress(tsv.encode())
        responses.add(responses.GET, NCBI_GENOME_SIZE_URL, body=compressed, status=200)
        result = get_ncbi_genome_size()
        assert "1280" in result
        assert result["1280"]["species_name"] == "Staphylococcus aureus"

    @responses.activate
    def test_failure_exits(self):
        responses.add(responses.GET, NCBI_GENOME_SIZE_URL, body="error", status=500)
        with pytest.raises(SystemExit):
            get_ncbi_genome_size()


class TestGetTaxidFromSpecies:
    @responses.activate
    def test_success(self):
        # The parser splits by newlines and looks for line.startswith("<Id>")
        xml = "<eSearchResult>\n<IdList>\n<Id>1280</Id>\n</IdList>\n</eSearchResult>\n"
        responses.add(
            responses.GET,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            body=xml,
            status=200,
        )
        result = get_taxid_from_species("Staphylococcus aureus")
        assert result == "1280"

    @responses.activate
    def test_failure_exits(self):
        responses.add(
            responses.GET,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            body="error",
            status=500,
        )
        with pytest.raises(SystemExit):
            get_taxid_from_species("Fake species")
