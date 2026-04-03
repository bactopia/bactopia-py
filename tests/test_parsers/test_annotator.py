"""Tests for bactopia.parsers.annotator."""

from bactopia.parsers.annotator import parse


class TestParse:
    def test_prokka(self, parser_fixtures):
        path = str(parser_fixtures / "annotator_prokka.txt")
        result = parse(path, "sample1")
        assert result["sample"] == "sample1"
        assert result["annotator_total_CDS"] == 2650
        assert result["annotator_total_rRNA"] == 6
        assert result["annotator_total_tRNA"] == 55

    def test_bakta(self, parser_fixtures):
        path = str(parser_fixtures / "annotator_bakta.txt")
        # bakta detection is based on "bakta" being in the path
        # so we need to ensure it's in the path string
        result = parse(path, "sample1")
        assert result["sample"] == "sample1"
        # bakta path doesn't have "bakta" in fixture filename by default,
        # so it uses PROKKA_METADATA. Let's test with a bakta-containing path.

    def test_bakta_path_detection(self, parser_fixtures, tmp_path):
        """Bakta is detected by 'bakta' appearing in the path."""
        bakta_dir = tmp_path / "bakta"
        bakta_dir.mkdir()
        bakta_file = bakta_dir / "sample1.txt"
        # Copy the bakta fixture content
        bakta_file.write_text((parser_fixtures / "annotator_bakta.txt").read_text())
        result = parse(str(bakta_file), "sample1")
        assert result["sample"] == "sample1"
        assert result["annotator_total_tRNAs"] == 55
        assert result["annotator_total_CDSs"] == 2650
        assert result["annotator_total_pseudogenes"] == 15

    def test_prokka_keys_prefixed(self, parser_fixtures):
        path = str(parser_fixtures / "annotator_prokka.txt")
        result = parse(path, "sample1")
        for key in result:
            if key != "sample":
                assert key.startswith("annotator_total_")
