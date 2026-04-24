"""Tests for bactopia.scaffold — template rendering library."""

import json

from bactopia.scaffold import (
    INPUT_TYPE_MAP,
    render_all_files,
    render_module_files,
    render_subworkflow_files,
    render_workflow_files,
    validate_config,
    write_files,
)


def _make_config(**overrides):
    """Create a minimal valid config for testing."""
    config = {
        "tool": "testtool",
        "display_name": "TestTool",
        "description": "A test tool",
        "process_name": "TESTTOOL",
        "package": "testtool",
        "version": "1.0.0",
        "build": "h12345_0",
        "home_url": "https://github.com/test/testtool",
        "input_type": "assembly",
        "has_database": False,
        "handles_gz": False,
        "layout": "flat",
        "resource_label": "process_low",
        "version_command": "testtool --version",
        "citation_key": "testtool",
        "keywords": ["test", "scaffold"],
        "aggregation": {"strategy": "csvtk_concat", "field": "tsv", "format": "tsv"},
        "outputs": [{"name": "tsv", "extension": "tsv", "description": "Test output"}],
        "parameters": [
            {
                "name": "testtool_opt",
                "type": "string",
                "default": "",
                "description": "An option",
                "flag": "--opt",
            }
        ],
        "container_refs": {
            "toolName": "bioconda::testtool=1.0.0",
            "docker": "biocontainers/testtool:1.0.0--h12345_0",
            "image": "https://depot.galaxyproject.org/singularity/testtool:1.0.0--h12345_0",
        },
    }
    config.update(overrides)
    return config


class TestValidateConfig:
    def test_valid_config(self):
        assert validate_config(_make_config()) == []

    def test_missing_field(self):
        config = _make_config()
        del config["tool"]
        errors = validate_config(config)
        assert any("tool" in e for e in errors)

    def test_invalid_input_type(self):
        errors = validate_config(_make_config(input_type="invalid"))
        assert any("input_type" in e for e in errors)

    def test_invalid_aggregation(self):
        errors = validate_config(_make_config(aggregation={"strategy": "invalid"}))
        assert any("aggregation" in e for e in errors)


class TestRenderModuleFiles:
    def test_produces_6_files(self):
        files = render_module_files(_make_config())
        assert len(files) == 6

    def test_file_paths(self):
        files = render_module_files(_make_config())
        expected = {
            "modules/testtool/main.nf",
            "modules/testtool/module.config",
            "modules/testtool/schema.json",
            "modules/testtool/tests/main.nf.test",
            "modules/testtool/tests/nextflow.config",
            "modules/testtool/tests/nf-test.config",
        }
        assert set(files.keys()) == expected

    def test_main_nf_contains_process(self):
        files = render_module_files(_make_config())
        main = files["modules/testtool/main.nf"]
        assert "process TESTTOOL {" in main
        assert "nextflow.preview.types = true" in main

    def test_module_config_contains_params(self):
        files = render_module_files(_make_config())
        config = files["modules/testtool/module.config"]
        assert "testtool_opt" in config
        assert "bioconda::testtool=1.0.0" in config

    def test_schema_json_valid(self):
        files = render_module_files(_make_config())
        schema = json.loads(files["modules/testtool/schema.json"])
        assert (
            schema["$defs"]["testtool_parameters"]["properties"]["testtool_opt"]["type"]
            == "string"
        )

    def test_database_input_adds_db_line(self):
        config = _make_config(
            has_database=True,
            database={
                "param_name": "testtool_db",
                "test_path": "datasets/test/db.tar.gz",
            },
        )
        files = render_module_files(config)
        main = files["modules/testtool/main.nf"]
        assert "db: Path" in main
        assert "is_tarball" in main


class TestRenderSubworkflowFiles:
    def test_produces_5_files(self):
        files = render_subworkflow_files(_make_config())
        assert len(files) == 5

    def test_csvtk_pattern(self):
        files = render_subworkflow_files(_make_config())
        main = files["subworkflows/testtool/main.nf"]
        assert "CSVTK_CONCAT" in main
        assert "gatherCsvtk" in main

    def test_no_aggregation_pattern(self):
        config = _make_config(aggregation={"strategy": "none"})
        files = render_subworkflow_files(config)
        main = files["subworkflows/testtool/main.nf"]
        assert "CSVTK_CONCAT" not in main
        assert "Channel.empty()" in main

    def test_database_passthrough(self):
        config = _make_config(
            has_database=True,
            database={
                "param_name": "testtool_db",
                "test_path": "datasets/test/db.tar.gz",
            },
        )
        files = render_subworkflow_files(config)
        main = files["subworkflows/testtool/main.nf"]
        assert "db: Path" in main
        assert ", db)" in main


class TestRenderWorkflowFiles:
    def test_produces_5_files(self):
        files = render_workflow_files(_make_config())
        assert len(files) == 5

    def test_output_block_present(self):
        files = render_workflow_files(_make_config())
        main = files["workflows/bactopia-tools/testtool/main.nf"]
        assert "output {" in main
        assert "sample_outputs" in main
        assert "run_outputs" in main
        assert "BACTOPIATOOL_INIT" in main

    def test_nextflow_config_structure(self):
        files = render_workflow_files(_make_config())
        config = files["workflows/bactopia-tools/testtool/nextflow.config"]
        assert "manifest {" in config
        assert 'name = "testtool"' in config
        assert "nf-bactopia@2.0.2" in config


class TestRenderAllFiles:
    def test_produces_16_files(self):
        files = render_all_files(_make_config())
        assert len(files) == 16

    def test_all_tiers_present(self):
        files = render_all_files(_make_config())
        paths = set(files.keys())
        assert any(p.startswith("modules/") for p in paths)
        assert any(p.startswith("subworkflows/") for p in paths)
        assert any(p.startswith("workflows/") for p in paths)


class TestWriteFiles:
    def test_creates_files(self, tmp_path):
        files = {"modules/test/main.nf": "content here"}
        created = write_files(files, tmp_path)
        assert created == ["modules/test/main.nf"]
        assert (tmp_path / "modules/test/main.nf").read_text() == "content here"

    def test_dry_run_does_not_create(self, tmp_path):
        files = {"modules/test/main.nf": "content here"}
        created = write_files(files, tmp_path, dry_run=True)
        assert created == ["modules/test/main.nf"]
        assert not (tmp_path / "modules/test/main.nf").exists()


class TestInputTypeMap:
    def test_all_types_have_required_keys(self):
        for itype, info in INPUT_TYPE_MAP.items():
            assert "channel" in info, f"{itype} missing 'channel'"
            assert "ext" in info, f"{itype} missing 'ext'"
            assert "record_fields" in info, f"{itype} missing 'record_fields'"
