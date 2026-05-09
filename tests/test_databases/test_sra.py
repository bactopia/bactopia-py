"""Tests for bactopia.databases.sra."""

import pandas as pd
import pytest

from bactopia.cli.search import parse_accessions
from bactopia.databases.sra import (
    instrument_to_platform,
    normalize_sra_fields,
)


class TestInstrumentToPlatform:
    def test_illumina_models(self):
        assert instrument_to_platform("Illumina HiSeq 2500") == "ILLUMINA"
        assert instrument_to_platform("Illumina MiSeq") == "ILLUMINA"
        assert instrument_to_platform("Illumina MiniSeq") == "ILLUMINA"
        assert instrument_to_platform("Illumina NovaSeq 6000") == "ILLUMINA"
        assert instrument_to_platform("NextSeq 500") == "ILLUMINA"

    def test_nanopore_models(self):
        assert instrument_to_platform("MinION") == "OXFORD_NANOPORE"
        assert instrument_to_platform("GridION") == "OXFORD_NANOPORE"
        assert instrument_to_platform("PromethION") == "OXFORD_NANOPORE"

    def test_pacbio_models(self):
        assert instrument_to_platform("PacBio RS II") == "PACBIO_SMRT"
        assert instrument_to_platform("Sequel II") == "PACBIO_SMRT"
        assert instrument_to_platform("Revio") == "PACBIO_SMRT"

    def test_ion_torrent(self):
        assert instrument_to_platform("Ion Torrent PGM") == "ION_TORRENT"

    def test_unknown_instrument(self):
        assert instrument_to_platform("SomeNewInstrument") == "SomeNewInstrument"

    def test_case_insensitive(self):
        assert instrument_to_platform("ILLUMINA HISEQ") == "ILLUMINA"
        assert instrument_to_platform("illumina miseq") == "ILLUMINA"


class TestNormalizeSraFields:
    def _make_record(self, **overrides):
        base = {
            "run_accession": "SRR38440076",
            "experiment_accession": "SRX33263877",
            "instrument": "Illumina MiniSeq",
            "instrument_model_desc": "ILLUMINA",
            "run_total_bases": 430446252,
            "run_total_spots": 1491140,
            "organism_taxid": 573,
            "organism_name": "Klebsiella pneumoniae",
            "library_layout": "PAIRED",
        }
        base.update(overrides)
        return base

    def test_field_renaming(self):
        records = [self._make_record()]
        result = normalize_sra_fields(records)
        assert len(result) == 1
        r = result[0]
        assert r["base_count"] == 430446252
        assert r["read_count"] == 1491140
        assert r["tax_id"] == 573
        assert r["scientific_name"] == "Klebsiella pneumoniae"
        assert "run_total_bases" not in r
        assert "run_total_spots" not in r
        assert "organism_taxid" not in r
        assert "organism_name" not in r

    def test_instrument_model_desc_preserved(self):
        records = [self._make_record()]
        result = normalize_sra_fields(records)
        assert result[0]["instrument_model_desc"] == "ILLUMINA"

    def test_instrument_model_desc_synthesized_when_missing(self):
        records = [self._make_record(instrument="MinION")]
        del records[0]["instrument_model_desc"]
        result = normalize_sra_fields(records)
        assert result[0]["instrument_model_desc"] == "OXFORD_NANOPORE"

    def test_fastq_bytes_paired(self):
        records = [self._make_record(library_layout="PAIRED")]
        result = normalize_sra_fields(records)
        assert result[0]["fastq_bytes"] == "0;0"

    def test_fastq_bytes_single(self):
        records = [self._make_record(library_layout="SINGLE")]
        result = normalize_sra_fields(records)
        assert result[0]["fastq_bytes"] == "0"

    def test_empty_records(self):
        assert normalize_sra_fields([]) == []

    def test_non_critical_fields_preserved(self):
        records = [self._make_record(bioproject="PRJNA288601", strain="unknown")]
        result = normalize_sra_fields(records)
        assert result[0]["bioproject"] == "PRJNA288601"
        assert result[0]["strain"] == "unknown"

    def test_experiment_accession_unchanged(self):
        records = [self._make_record()]
        result = normalize_sra_fields(records)
        assert result[0]["experiment_accession"] == "SRX33263877"


class TestGetSraMetadata:
    def test_success(self, mocker):
        mock_df = pd.DataFrame(
            [
                {
                    "run_accession": "SRR38440076",
                    "experiment_accession": "SRX33263877",
                    "instrument": "Illumina MiniSeq",
                    "instrument_model_desc": "ILLUMINA",
                    "run_total_bases": 430446252,
                    "run_total_spots": 1491140,
                    "organism_taxid": 573,
                    "organism_name": "Klebsiella pneumoniae",
                    "library_layout": "PAIRED",
                }
            ]
        )
        mock_db = mocker.MagicMock()
        mock_db.search_sra.return_value = mock_df
        mocker.patch("bactopia.databases.sra.SRAweb", return_value=mock_db)

        from bactopia.databases.sra import get_sra_metadata

        success, data = get_sra_metadata("SRR38440076", is_accession=True, limit=10)
        assert success is True
        assert len(data) == 1
        assert data[0]["base_count"] == 430446252
        assert data[0]["fastq_bytes"] == "0;0"

    def test_no_results(self, mocker):
        mock_db = mocker.MagicMock()
        mock_db.search_sra.return_value = None
        mocker.patch("bactopia.databases.sra.SRAweb", return_value=mock_db)

        from bactopia.databases.sra import get_sra_metadata

        success, data = get_sra_metadata("DOESNOTEXIST", is_accession=True, limit=10)
        assert success is False
        assert data == []

    def test_empty_dataframe(self, mocker):
        mock_db = mocker.MagicMock()
        mock_db.search_sra.return_value = pd.DataFrame()
        mocker.patch("bactopia.databases.sra.SRAweb", return_value=mock_db)

        from bactopia.databases.sra import get_sra_metadata

        success, data = get_sra_metadata("DOESNOTEXIST", is_accession=True, limit=10)
        assert success is False
        assert data == []

    def test_network_error(self, mocker):
        mock_db = mocker.MagicMock()
        mock_db.search_sra.side_effect = ConnectionError("network down")
        mocker.patch("bactopia.databases.sra.SRAweb", return_value=mock_db)

        from bactopia.databases.sra import get_sra_metadata

        success, data = get_sra_metadata("SRR38440076", is_accession=True, limit=10)
        assert success is False
        assert data == []

    def test_limit_truncation(self, mocker):
        mock_df = pd.DataFrame(
            [
                {
                    "run_accession": f"SRR{i}",
                    "experiment_accession": f"SRX{i}",
                    "instrument": "Illumina MiSeq",
                    "instrument_model_desc": "ILLUMINA",
                    "run_total_bases": 100,
                    "run_total_spots": 10,
                    "organism_taxid": 573,
                    "organism_name": "Klebsiella pneumoniae",
                    "library_layout": "PAIRED",
                }
                for i in range(10)
            ]
        )
        mock_db = mocker.MagicMock()
        mock_db.search_sra.return_value = mock_df
        mocker.patch("bactopia.databases.sra.SRAweb", return_value=mock_db)

        from bactopia.databases.sra import get_sra_metadata

        success, data = get_sra_metadata("SRR38440076", is_accession=True, limit=3)
        assert success is True
        assert len(data) == 3


class TestProviderParity:
    """Verify parse_accessions produces identical output from ENA and SRA data.

    Uses real field values from ERR14835505 (ONT), SRR38397820 (Illumina),
    and SRR37720934 (PacBio) captured from both providers.
    """

    def _parse(self, results):
        return parse_accessions(
            results,
            min_read_length=0,
            min_base_count=0,
            genome_size=0,
            genome_sizes=None,
        )

    def test_ont_ERR14835505_parity(self):
        ena_record = {
            "experiment_accession": "ERX14241383",
            "instrument_platform": "OXFORD_NANOPORE",
            "base_count": "498252775",
            "read_count": "101506",
            "fastq_bytes": "452691802",
            "tax_id": "1280",
            "scientific_name": "Staphylococcus aureus",
            "library_layout": "SINGLE",
        }
        sra_record = normalize_sra_fields(
            [
                {
                    "experiment_accession": "ERX14241383",
                    "instrument": "GridION",
                    "instrument_model_desc": "OXFORD_NANOPORE",
                    "run_total_bases": 498252775,
                    "run_total_spots": 101506,
                    "organism_taxid": 1280,
                    "organism_name": "Staphylococcus aureus",
                    "library_layout": "SINGLE",
                }
            ]
        )[0]

        ena_accessions, _ = self._parse([ena_record])
        sra_accessions, _ = self._parse([sra_record])
        assert ena_accessions == sra_accessions
        assert len(ena_accessions) == 1
        assert "ont" in ena_accessions[0]

    def test_illumina_SRR38397820_parity(self):
        sra_record = normalize_sra_fields(
            [
                {
                    "experiment_accession": "SRX33229631",
                    "instrument": "NextSeq 550",
                    "instrument_model_desc": "ILLUMINA",
                    "run_total_bases": 514321622,
                    "run_total_spots": 1755969,
                    "organism_taxid": 1280,
                    "organism_name": "Staphylococcus aureus",
                    "library_layout": "PAIRED",
                }
            ]
        )[0]

        sra_accessions, sra_filtered = self._parse([sra_record])
        assert len(sra_accessions) == 1
        assert "illumina" in sra_accessions[0]
        assert "SRX33229631" in sra_accessions[0]

    def test_illumina_SRR38397820_ena_sync_delay(self):
        """ENA returns base_count=0 and empty fastq_bytes for this accession,
        demonstrating the sync delay that motivates the SRA fallback."""
        ena_record = {
            "experiment_accession": "SRX33229631",
            "instrument_platform": "ILLUMINA",
            "base_count": "0",
            "read_count": "0",
            "fastq_bytes": "",
            "tax_id": "1280",
            "scientific_name": "Staphylococcus aureus",
            "library_layout": "PAIRED",
        }
        ena_accessions, ena_filtered = self._parse([ena_record])
        assert len(ena_accessions) == 0
        assert ena_filtered["technical"] == 1

        sra_record = normalize_sra_fields(
            [
                {
                    "experiment_accession": "SRX33229631",
                    "instrument": "NextSeq 550",
                    "instrument_model_desc": "ILLUMINA",
                    "run_total_bases": 514321622,
                    "run_total_spots": 1755969,
                    "organism_taxid": 1280,
                    "organism_name": "Staphylococcus aureus",
                    "library_layout": "PAIRED",
                }
            ]
        )[0]
        sra_accessions, _ = self._parse([sra_record])
        assert len(sra_accessions) == 1

    def test_pacbio_SRR37720934_filtered_both_providers(self):
        """PacBio is not supported by Bactopia -- filtered out from both providers."""
        ena_record = {
            "experiment_accession": "SRX32598386",
            "instrument_platform": "PACBIO_SMRT",
            "base_count": "113672335",
            "read_count": "76134",
            "fastq_bytes": "23713360",
            "tax_id": "",
            "scientific_name": "",
            "library_layout": "SINGLE",
        }
        sra_record = normalize_sra_fields(
            [
                {
                    "experiment_accession": "SRX32598386",
                    "instrument": "PacBio RS",
                    "instrument_model_desc": "PACBIO_SMRT",
                    "run_total_bases": 113672335,
                    "run_total_spots": 76134,
                    "organism_taxid": 1280,
                    "organism_name": "Staphylococcus aureus",
                    "library_layout": "SINGLE",
                }
            ]
        )[0]

        ena_accessions, _ = self._parse([ena_record])
        sra_accessions, _ = self._parse([sra_record])
        assert ena_accessions == []
        assert sra_accessions == []
