"""Tests for bactopia.parsers.parsables."""

from bactopia.parsers.parsables import get_parsable_files


class TestGetParsableFiles:
    def test_complete(self, tmp_path):
        """When all expected files exist, returns [True, dict]."""
        name = "s1"
        base = tmp_path / name
        # Create all required files
        (base / "main" / "assembler").mkdir(parents=True)
        (base / "main" / "assembler" / f"{name}.tsv").write_text("data")
        (base / "main" / "gather").mkdir(parents=True)
        (base / "main" / "gather" / f"{name}-meta.tsv").write_text("data")
        (base / "main" / "sketcher").mkdir(parents=True)
        (base / "main" / "sketcher" / f"{name}-mash-refseq88-k21.txt").write_text(
            "data"
        )
        (base / "main" / "sketcher" / f"{name}-sourmash-gtdb-rs207-k31.txt").write_text(
            "data"
        )
        (base / "tools" / "amrfinderplus").mkdir(parents=True)
        (base / "tools" / "amrfinderplus" / f"{name}.tsv").write_text("data")
        (base / "tools" / "mlst").mkdir(parents=True)
        (base / "tools" / "mlst" / f"{name}.tsv").write_text("data")
        (base / "main" / "annotator" / "prokka").mkdir(parents=True)
        (base / "main" / "annotator" / "prokka" / f"{name}.txt").write_text("data")

        is_complete, parsable = get_parsable_files(str(base), name)
        assert is_complete is True
        assert isinstance(parsable, dict)

    def test_incomplete(self, tmp_path):
        """When files are missing, returns [False, list_of_missing]."""
        name = "s1"
        base = tmp_path / name
        base.mkdir()

        is_complete, missing = get_parsable_files(str(base), name)
        assert is_complete is False
        assert isinstance(missing, list)
        assert len(missing) > 0
