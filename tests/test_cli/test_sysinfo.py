"""Functional tests for the bactopia-sysinfo CLI."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from bactopia.cli.sysinfo import sysinfo


@pytest.fixture
def host():
    """Mock psutil to a configurable host shape (RAM in GB, logical CPUs)."""

    class _Host:
        def __init__(self, mem_gb=64, cpus=16):
            self.mem_gb = mem_gb
            self.cpus = cpus

        def __enter__(self):
            self._vmem = patch(
                "bactopia.cli.sysinfo.psutil.virtual_memory",
                return_value=type("VM", (), {"total": self.mem_gb * 1024**3})(),
            )
            self._cpu = patch(
                "bactopia.cli.sysinfo.psutil.cpu_count",
                return_value=self.cpus,
            )
            self._vmem.start()
            self._cpu.start()
            return self

        def __exit__(self, *_):
            self._vmem.stop()
            self._cpu.stop()

    return _Host


def _invoke(args):
    return CliRunner().invoke(sysinfo, args)


class TestEligibility:
    def test_default_profile_emits_both(self, host):
        with host(mem_gb=64, cpus=8):
            result = _invoke(["--wf", "bactopia"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "--max_memory 63.GB --max_cpus 8"

    def test_small_host_caps_to_total_minus_one(self, host):
        with host(mem_gb=8, cpus=4):
            result = _invoke(["--wf", "bactopia"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "--max_memory 7.GB --max_cpus 4"

    def test_under_floor_skips_memory_only(self, host):
        with host(mem_gb=2, cpus=2):
            result = _invoke(["--wf", "bactopia"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "--max_cpus 2"
        assert "below floor" in result.stderr

    def test_user_set_max_memory(self, host):
        with host(mem_gb=64, cpus=8):
            result = _invoke(["-profile", "docker", "--max_memory", "16.GB"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "--max_cpus 8"

    def test_user_set_both(self, host):
        with host(mem_gb=64, cpus=16):
            result = _invoke(
                ["-profile", "docker", "--max_memory", "16.GB", "--max_cpus", "8"]
            )
        assert result.exit_code == 0
        assert result.stdout == ""


class TestProfileGate:
    def test_test_profile_excluded(self, host):
        with host(mem_gb=64, cpus=16):
            result = _invoke(["-profile", "test"])
        assert result.exit_code == 0
        assert result.stdout == ""

    def test_arcc_profile_excluded(self, host):
        with host(mem_gb=64, cpus=16):
            result = _invoke(["-profile", "arcc"])
        assert result.exit_code == 0
        assert result.stdout == ""

    def test_composed_local_profiles(self, host):
        with host(mem_gb=64, cpus=8):
            result = _invoke(["-profile", "docker,wave"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "--max_memory 63.GB --max_cpus 8"

    def test_one_unknown_in_composed_profile_excludes(self, host):
        with host(mem_gb=64, cpus=16):
            result = _invoke(["-profile", "docker,slurm"])
        assert result.exit_code == 0
        assert result.stdout == ""

    def test_custom_config_with_c(self, host):
        with host(mem_gb=64, cpus=16):
            result = _invoke(["-c", "custom.config"])
        assert result.exit_code == 0
        assert result.stdout == ""

    def test_custom_config_with_nfconfig(self, host):
        with host(mem_gb=64, cpus=16):
            result = _invoke(["--nfconfig", "custom.config"])
        assert result.exit_code == 0
        assert result.stdout == ""


class TestFlagParsingForms:
    def test_max_memory_equals_form(self, host):
        with host(mem_gb=64, cpus=8):
            result = _invoke(["--max_memory=8.GB"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "--max_cpus 8"

    def test_profile_equals_form(self, host):
        with host(mem_gb=64, cpus=8):
            result = _invoke(["-profile=docker"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "--max_memory 63.GB --max_cpus 8"

    def test_max_cpus_equals_form(self, host):
        with host(mem_gb=64, cpus=16):
            result = _invoke(["--max_cpus=4"])
        assert result.exit_code == 0
        assert result.stdout.strip() == "--max_memory 63.GB"


class TestInformationalInvocations:
    def test_no_args_emits_detected(self, host):
        with host(mem_gb=64, cpus=8):
            result = _invoke([])
        assert result.exit_code == 0
        assert result.stdout.strip() == "--max_memory 63.GB --max_cpus 8"

    def test_help_alone_emits_nothing(self, host):
        with host():
            result = _invoke(["--help"])
        assert result.exit_code == 0
        assert result.stdout == ""

    def test_version_alone(self, host):
        with host():
            result = _invoke(["--version"])
        assert result.exit_code == 0
        assert "bactopia-sysinfo" in result.stdout

    def test_help_among_args_emits_nothing(self, host):
        with host(mem_gb=64, cpus=16):
            result = _invoke(["--wf", "bactopia", "--help"])
        assert result.exit_code == 0
        assert result.stdout == ""

    def test_list_wfs_emits_nothing(self, host):
        with host(mem_gb=64, cpus=16):
            result = _invoke(["--list_wfs"])
        assert result.exit_code == 0
        assert result.stdout == ""
