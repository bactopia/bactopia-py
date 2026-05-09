"""Tests for bactopia.databases.ena."""

import responses

from bactopia.databases.ena import ENA_URL, get_ena_metadata, get_run_info


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


class TestGetRunInfo:
    @responses.activate
    def test_returns_3_tuple(self):
        body = "run_accession\nSRR123\n"
        responses.add(responses.POST, ENA_URL, body=body, status=200)
        result = get_run_info("SRR123", "SRR123", is_accession=True, limit=10)
        assert len(result) == 3
        success, data, source = result
        assert success is True
        assert source == "ena"

    @responses.activate
    def test_ena_success_returns_ena_source(self):
        body = "run_accession\nSRR123\n"
        responses.add(responses.POST, ENA_URL, body=body, status=200)
        success, data, source = get_run_info(
            "SRR123", "SRR123", is_accession=True, limit=10
        )
        assert success is True
        assert len(data) == 1
        assert source == "ena"

    @responses.activate
    def test_only_provider_ena_no_fallback(self):
        responses.add(responses.POST, ENA_URL, body="", status=200)
        success, data, source = get_run_info(
            "SRR123", "SRR123", is_accession=True, limit=10, only_provider=True
        )
        assert success is False
        assert data == []
        assert source == "none"

    @responses.activate
    def test_provider_sra(self, mocker):
        mock_sra = mocker.patch(
            "bactopia.databases.sra.get_sra_metadata",
            return_value=[True, [{"run_accession": "SRR123"}]],
        )
        success, data, source = get_run_info(
            "SRR123", "SRR123", is_accession=True, limit=10, provider="sra"
        )
        assert success is True
        assert source == "sra"
        mock_sra.assert_called_once()

    @responses.activate
    def test_only_provider_sra_no_fallback(self, mocker):
        mocker.patch(
            "bactopia.databases.sra.get_sra_metadata",
            return_value=[False, []],
        )
        success, data, source = get_run_info(
            "SRR123",
            "SRR123",
            is_accession=True,
            limit=10,
            provider="sra",
            only_provider=True,
        )
        assert success is False
        assert source == "none"

    @responses.activate
    def test_fallback_to_sra_on_empty_ena(self, mocker):
        responses.add(responses.POST, ENA_URL, body="", status=200)
        mocker.patch(
            "bactopia.databases.sra.get_sra_metadata",
            return_value=[True, [{"run_accession": "SRR123"}]],
        )
        success, data, source = get_run_info(
            "SRR123", "SRR123", is_accession=True, limit=10
        )
        assert success is True
        assert source == "sra"

    @responses.activate
    def test_fallback_to_sra_on_ena_error(self, mocker):
        responses.add(responses.POST, ENA_URL, body="error", status=500)
        mocker.patch(
            "bactopia.databases.sra.get_sra_metadata",
            return_value=[True, [{"run_accession": "SRR123"}]],
        )
        success, data, source = get_run_info(
            "SRR123", "SRR123", is_accession=True, limit=10
        )
        assert success is True
        assert source == "sra"

    @responses.activate
    def test_provider_sra_fallback_to_ena(self, mocker):
        body = "run_accession\nSRR123\n"
        responses.add(responses.POST, ENA_URL, body=body, status=200)
        mocker.patch(
            "bactopia.databases.sra.get_sra_metadata",
            return_value=[False, []],
        )
        success, data, source = get_run_info(
            "SRR123", "SRR123", is_accession=True, limit=10, provider="sra"
        )
        assert success is True
        assert source == "ena"

    @responses.activate
    def test_both_fail(self, mocker):
        responses.add(responses.POST, ENA_URL, body="error", status=500)
        mocker.patch(
            "bactopia.databases.sra.get_sra_metadata",
            return_value=[False, []],
        )
        success, data, source = get_run_info(
            "SRR123", "SRR123", is_accession=True, limit=10
        )
        assert success is False
        assert source == "none"
