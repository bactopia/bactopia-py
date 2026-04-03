"""Tests for bactopia.parse."""

from pathlib import Path

from bactopia.parse import _is_bactopia_dir, parse_bactopia_directory


class TestIsBactopiaDir:
    def test_true(self, sample_bactopia_dir):
        path = sample_bactopia_dir / "sample1"
        assert _is_bactopia_dir(path, "sample1") is True

    def test_false(self, tmp_path):
        (tmp_path / "not_bactopia").mkdir()
        assert _is_bactopia_dir(tmp_path / "not_bactopia", "not_bactopia") is False


class TestParseBactopiaDirectory:
    def test_valid_directory(self, sample_bactopia_dir):
        results = parse_bactopia_directory(str(sample_bactopia_dir))
        assert len(results) == 1
        assert results[0]["id"] == "sample1"
        assert results[0]["is_bactopia"] is True

    def test_ignores_dotfiles(self, tmp_path):
        (tmp_path / ".nextflow").mkdir()
        (tmp_path / "sample1" / "main" / "gather").mkdir(parents=True)
        (tmp_path / "sample1" / "main" / "gather" / "sample1-meta.tsv").write_text("x")
        results = parse_bactopia_directory(str(tmp_path))
        ids = [r["id"] for r in results]
        assert ".nextflow" not in ids
        assert "sample1" in ids

    def test_not_bactopia_dir(self, tmp_path):
        (tmp_path / "random_dir").mkdir()
        results = parse_bactopia_directory(str(tmp_path))
        assert len(results) == 1
        assert results[0]["is_bactopia"] is False

    def test_empty_directory(self, tmp_path):
        results = parse_bactopia_directory(str(tmp_path))
        assert results == []
