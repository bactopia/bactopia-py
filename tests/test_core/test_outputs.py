"""Tests for bactopia.outputs."""

from pathlib import Path

from bactopia.outputs import filter_ignored, load_ignore_patterns, scan_work_dir


class TestScanWorkDir:
    def test_excludes_symlinks(self, tmp_path):
        real = tmp_path / "real.txt"
        real.write_text("data")
        link = tmp_path / "link.txt"
        link.symlink_to(real)
        result = scan_work_dir(tmp_path)
        assert "real.txt" in result
        assert "link.txt" not in result

    def test_excludes_nextflow_internals(self, tmp_path):
        (tmp_path / ".command.sh").write_text("#!/bin/bash")
        (tmp_path / ".exitcode").write_text("0")
        (tmp_path / "output.bam").write_text("data")
        result = scan_work_dir(tmp_path)
        assert "output.bam" in result
        assert ".command.sh" not in result
        assert ".exitcode" not in result

    def test_sorted_output(self, tmp_path):
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "a.txt").write_text("a")
        result = scan_work_dir(tmp_path)
        assert result == ["a.txt", "b.txt"]


class TestFilterIgnored:
    def test_no_patterns(self):
        kept, ignored = filter_ignored(["a.txt", "b.txt"], [])
        assert kept == ["a.txt", "b.txt"]
        assert ignored == []

    def test_glob_pattern(self):
        files = ["output.bam", "output.bai", "staging/input.fastq"]
        kept, ignored = filter_ignored(files, ["staging/*"])
        assert "staging/input.fastq" in ignored
        assert "output.bam" in kept

    def test_wildcard_pattern(self):
        files = ["a.log", "b.log", "c.txt"]
        kept, ignored = filter_ignored(files, ["*.log"])
        assert kept == ["c.txt"]
        assert set(ignored) == {"a.log", "b.log"}


class TestLoadIgnorePatterns:
    def test_file_exists(self, tmp_path):
        ignore = tmp_path / ".outputs-ignore"
        ignore.write_text("# comment\n\n*.log\nstaging/**\n")
        result = load_ignore_patterns(tmp_path)
        assert result == ["*.log", "staging/**"]

    def test_file_missing(self, tmp_path):
        result = load_ignore_patterns(tmp_path)
        assert result == []
