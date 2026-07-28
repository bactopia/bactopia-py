"""Tests for bactopia.nf.read_versions."""

import pytest

from bactopia.nf import read_versions


def test_reads_and_normalizes_keys(tmp_path):
    (tmp_path / "versions.yml").write_text("bactopia: 9.9.9\nnf-bactopia: 1.2.3\n")
    assert read_versions(tmp_path) == {"bactopia": "9.9.9", "nf_bactopia": "1.2.3"}


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_versions(tmp_path)


def test_missing_key_raises(tmp_path):
    (tmp_path / "versions.yml").write_text("bactopia: 9.9.9\n")
    with pytest.raises(KeyError):
        read_versions(tmp_path)
