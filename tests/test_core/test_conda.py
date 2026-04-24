"""Tests for bactopia.conda — shared Anaconda API client."""

import responses

from bactopia.conda import (
    ANACONDA_API_BASE,
    check_component_exists,
    construct_container_refs,
    get_latest_info,
    get_latest_info_with_fallback,
)

BIOCONDA_URL = f"{ANACONDA_API_BASE}/bioconda/mlst"
CONDA_FORGE_URL = f"{ANACONDA_API_BASE}/conda-forge/pigz"


def _make_api_response(
    name="mlst",
    version="2.23.0",
    build="hdfd78af_0",
    subdir="linux-64",
    summary="Scan contig files against PubMLST typing schemes",
    home="https://github.com/tseemann/mlst",
):
    return {
        "name": name,
        "latest_version": version,
        "summary": summary,
        "home": home,
        "files": [
            {
                "version": version,
                "attrs": {"subdir": subdir, "build": build},
            }
        ],
    }


class TestGetLatestInfo:
    @responses.activate
    def test_successful_bioconda_lookup(self):
        responses.add(
            responses.GET,
            BIOCONDA_URL,
            json=_make_api_response(),
            status=200,
        )
        result = get_latest_info("mlst", max_retry=1, channel="bioconda")
        assert result is not None
        assert result["version"] == "2.23.0"
        assert result["build"] == "hdfd78af_0"
        assert result["summary"] == "Scan contig files against PubMLST typing schemes"
        assert result["home"] == "https://github.com/tseemann/mlst"

    @responses.activate
    def test_noarch_fallback(self):
        responses.add(
            responses.GET,
            BIOCONDA_URL,
            json=_make_api_response(subdir="noarch"),
            status=200,
        )
        result = get_latest_info("mlst", max_retry=1, channel="bioconda")
        assert result is not None
        assert result["build"] == "hdfd78af_0"

    @responses.activate
    def test_no_matching_build(self):
        data = _make_api_response(subdir="osx-64")
        responses.add(responses.GET, BIOCONDA_URL, json=data, status=200)
        result = get_latest_info("mlst", max_retry=1, channel="bioconda")
        assert result is not None
        assert result["version"] == "2.23.0"
        assert result["build"] is None

    @responses.activate
    def test_package_not_found(self):
        responses.add(responses.GET, BIOCONDA_URL, status=404)
        result = get_latest_info("mlst", max_retry=1, channel="bioconda")
        assert result is None

    @responses.activate
    def test_retry_then_succeed(self):
        responses.add(responses.GET, BIOCONDA_URL, status=500)
        responses.add(
            responses.GET,
            BIOCONDA_URL,
            json=_make_api_response(),
            status=200,
        )
        result = get_latest_info("mlst", max_retry=2, channel="bioconda")
        assert result is not None
        assert result["version"] == "2.23.0"
        assert len(responses.calls) == 2

    @responses.activate
    def test_all_retries_exhausted(self):
        responses.add(responses.GET, BIOCONDA_URL, status=500)
        responses.add(responses.GET, BIOCONDA_URL, status=500)
        result = get_latest_info("mlst", max_retry=2, channel="bioconda")
        assert result is None


class TestGetLatestInfoWithFallback:
    @responses.activate
    def test_found_on_bioconda(self):
        responses.add(
            responses.GET,
            f"{ANACONDA_API_BASE}/bioconda/mlst",
            json=_make_api_response(),
            status=200,
        )
        result = get_latest_info_with_fallback("mlst", max_retry=1)
        assert result is not None
        assert result["channel"] == "bioconda"

    @responses.activate
    def test_fallback_to_conda_forge(self):
        responses.add(
            responses.GET,
            f"{ANACONDA_API_BASE}/bioconda/pigz",
            status=404,
        )
        responses.add(
            responses.GET,
            CONDA_FORGE_URL,
            json=_make_api_response(name="pigz", version="2.8"),
            status=200,
        )
        result = get_latest_info_with_fallback("pigz", max_retry=1)
        assert result is not None
        assert result["channel"] == "conda-forge"
        assert result["version"] == "2.8"

    @responses.activate
    def test_not_found_anywhere(self):
        responses.add(
            responses.GET,
            f"{ANACONDA_API_BASE}/bioconda/nonexistent",
            status=404,
        )
        responses.add(
            responses.GET,
            f"{ANACONDA_API_BASE}/conda-forge/nonexistent",
            status=404,
        )
        result = get_latest_info_with_fallback("nonexistent", max_retry=1)
        assert result is None


class TestConstructContainerRefs:
    def test_with_build(self):
        refs = construct_container_refs("mlst", "2.23.0", "hdfd78af_0")
        assert refs["toolName"] == "bioconda::mlst=2.23.0"
        assert refs["docker"] == "biocontainers/mlst:2.23.0--hdfd78af_0"
        assert refs["image"] == (
            "https://depot.galaxyproject.org/singularity/mlst:2.23.0--hdfd78af_0"
        )

    def test_without_build(self):
        refs = construct_container_refs("mlst", "2.23.0", None)
        assert refs["toolName"] == "bioconda::mlst=2.23.0"
        assert "TODO_BUILD" in refs["docker"]
        assert "TODO_BUILD" in refs["image"]


class TestCheckComponentExists:
    def test_nothing_exists(self, tmp_path):
        bp = tmp_path / "bactopia"
        (bp / "modules").mkdir(parents=True)
        (bp / "subworkflows").mkdir(parents=True)
        (bp / "workflows" / "bactopia-tools").mkdir(parents=True)

        result = check_component_exists(bp, "newtool")
        assert result == {"module": False, "subworkflow": False, "workflow": False}

    def test_all_exist(self, tmp_path):
        bp = tmp_path / "bactopia"
        (bp / "modules" / "mlst").mkdir(parents=True)
        (bp / "subworkflows" / "mlst").mkdir(parents=True)
        (bp / "workflows" / "bactopia-tools" / "mlst").mkdir(parents=True)

        result = check_component_exists(bp, "mlst")
        assert result == {"module": True, "subworkflow": True, "workflow": True}

    def test_partial_exists(self, tmp_path):
        bp = tmp_path / "bactopia"
        (bp / "modules" / "mlst").mkdir(parents=True)
        (bp / "subworkflows").mkdir(parents=True)
        (bp / "workflows" / "bactopia-tools").mkdir(parents=True)

        result = check_component_exists(bp, "mlst")
        assert result == {"module": True, "subworkflow": False, "workflow": False}
