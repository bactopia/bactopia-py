"""CLI smoke tests: verify all commands load and respond to --help."""

import importlib

import pytest
from click.testing import CliRunner

# (module_path, click_function_name)
CLI_COMMANDS = [
    ("bactopia.cli.citations", "citations"),
    ("bactopia.cli.datasets", "datasets"),
    ("bactopia.cli.download", "download"),
    ("bactopia.cli.prepare", "prepare"),
    ("bactopia.cli.search", "search"),
    ("bactopia.cli.summary", "summary"),
    ("bactopia.cli.update", "update"),
    ("bactopia.cli.status", "status"),
    ("bactopia.cli.sysinfo", "sysinfo"),
    ("bactopia.cli.workflows", "download"),
    ("bactopia.cli.atb.atb_formatter", "atb_formatter"),
    ("bactopia.cli.atb.atb_downloader", "atb_downloader"),
    ("bactopia.cli.helpers.merge_schemas", "merge_schemas"),
    ("bactopia.cli.pubmlst.setup", "pubmlst_setup"),
    ("bactopia.cli.prune", "prune"),
    ("bactopia.cli.pubmlst.build", "pubmlst_download"),
    ("bactopia.cli.testing", "testing"),
    ("bactopia.cli.lint", "lint"),
    ("bactopia.cli.catalog", "catalog"),
    ("bactopia.cli.review", "review"),
    # Pipeline utilities
    ("bactopia.cli.pipeline.check_fastqs", "check_fastqs"),
    ("bactopia.cli.pipeline.check_assembly_accession", "check_assembly_accession"),
    ("bactopia.cli.pipeline.cleanup_coverage", "cleanup_coverage"),
    ("bactopia.cli.pipeline.mask_consensus", "mask_consensus"),
    ("bactopia.cli.pipeline.kraken_bracken_summary", "kraken_bracken_summary"),
    ("bactopia.cli.pipeline.scrubber_summary", "scrubber_summary"),
    ("bactopia.cli.pipeline.teton_prepare", "teton_prepare"),
    ("bactopia.cli.pipeline.bracken_to_excel", "bracken_to_excel"),
]


def _get_click_cmd(module_path, func_name):
    """Import module and return the click command function."""
    mod = importlib.import_module(module_path)
    return getattr(mod, func_name)


@pytest.mark.parametrize(
    "module_path,func_name",
    CLI_COMMANDS,
    ids=[f"{m.split('.')[-1]}.{f}" for m, f in CLI_COMMANDS],
)
def test_help(module_path, func_name):
    """Every CLI command loads and prints help without error."""
    cmd = _get_click_cmd(module_path, func_name)
    runner = CliRunner()
    result = runner.invoke(cmd, ["--help"])
    assert result.exit_code == 0, f"--help failed:\n{result.output}"
