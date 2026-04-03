"""Global test fixtures and markers for bactopia-py."""

import os
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir():
    """Path to the in-repo test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def parser_fixtures():
    """Path to parser-specific test fixtures."""
    return FIXTURES_DIR / "parsers"


def _resolve_env_path(var_name):
    """Return Path if env var is set and directory exists, else None."""
    val = os.environ.get(var_name)
    if val and Path(val).is_dir():
        return Path(val)
    return None


@pytest.fixture
def bactopia_results():
    """Path to the bactopia-results data directory.

    Returns None if BACTOPIA_RESULTS is not set.
    """
    return _resolve_env_path("BACTOPIA_RESULTS")


# Skip decorators for integration tests
requires_bactopia_results = pytest.mark.skipif(
    not os.environ.get("BACTOPIA_RESULTS")
    or not Path(os.environ.get("BACTOPIA_RESULTS", "")).is_dir(),
    reason="BACTOPIA_RESULTS env var not set or directory missing",
)


@pytest.fixture
def rank_cutoff():
    """Default rank cutoff dict matching Bactopia summary defaults."""
    return {
        "gold": {"coverage": 100, "quality": 30, "length": 95, "contigs": 100},
        "silver": {"coverage": 50, "quality": 20, "length": 75, "contigs": 200},
        "bronze": {"coverage": 20, "quality": 12, "length": 49, "contigs": 500},
        "min-assembled-size": None,
        "max-assembled-size": None,
    }


@pytest.fixture
def pipeline_fixtures():
    """Path to pipeline-specific test fixtures."""
    return FIXTURES_DIR / "parsers" / "pipeline"


@pytest.fixture
def sample_bactopia_dir():
    """Path to the minimal simulated Bactopia output in fixtures."""
    return FIXTURES_DIR / "bactopia_dir"
