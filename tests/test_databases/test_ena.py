"""Tests for bactopia.databases.ena."""

import responses

from bactopia.databases.ena import ENA_URL, get_ena_metadata


class TestGetEnaMetadata:
    @responses.activate
    def test_success(self):
        body = "run_accession\tsample_accession\nSRR123\tSAMN456\n"
        responses.add(responses.POST, ENA_URL, body=body, status=200)
        success, data = get_ena_metadata("SRR123", is_accession=True, limit=10)
        assert success is True
        assert len(data) == 1
        assert data[0]["run_accession"] == "SRR123"

    @responses.activate
    def test_failure(self):
        responses.add(responses.POST, ENA_URL, body="error", status=500)
        success, data = get_ena_metadata("bad_query", is_accession=False, limit=10)
        assert success is False
        assert data[0] == 500

    @responses.activate
    def test_accession_mode(self):
        body = "run_accession\nSRR123\n"
        responses.add(responses.POST, ENA_URL, body=body, status=200)
        success, data = get_ena_metadata("SRR123", is_accession=True, limit=10)
        assert success is True
        # Verify includeAccessions was used (check the request body)
        assert "includeAccessions" in responses.calls[0].request.body

    @responses.activate
    def test_query_mode(self):
        body = "run_accession\nSRR123\n"
        responses.add(responses.POST, ENA_URL, body=body, status=200)
        success, data = get_ena_metadata("1280", is_accession=False, limit=10)
        assert success is True
        assert "query" in responses.calls[0].request.body
