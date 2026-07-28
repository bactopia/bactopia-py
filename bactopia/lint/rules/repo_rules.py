"""Repo-level lint rules for Bactopia (V001).

These rules check invariants that span the whole repository rather than a
single component -- currently that every version-bearing file agrees with the
declared source of truth, ``versions.yml``.
"""

import json
import re
from pathlib import Path

from bactopia.lint.models import LintResult
from bactopia.nf import read_versions

_PLUGIN_PIN_RE = re.compile(r"id\s+['\"]nf-bactopia@([^'\"]+)['\"]")
_VERSION_RE = re.compile(r"bactopia_version\s*=\s*'([^']+)'")
_CHANGELOG_RE = re.compile(r"^##\s+v?(\d+\.\d+\.\d+)\b", re.MULTILINE)
_GRADLE_VERSION_RE = re.compile(r"^version\s*=\s*'([^']+)'", re.MULTILINE)
_SKIP_DIRS = {
    ".git",
    "work",
    ".nextflow",
    ".nf-test",
    "node_modules",
    "temp",
    "temp-test",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    ".gradle",
}


def _fail(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "FAIL", component, msg)


def _pass(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "PASS", component, msg)


def _warn(rule_id: str, component: str, msg: str) -> LintResult:
    return LintResult(rule_id, "WARN", component, msg)


def rule_v001(component: str, ctx: dict) -> list[LintResult]:
    """Version-bearing files match versions.yml.

    Confirms the pipeline version (nextflow.config, catalog.json, bin/bactopia,
    data/conda/meta.yaml, CITATION.cff) and the nf-bactopia plugin pin (every
    *.config, catalog.json) equal the values declared in versions.yml.
    """
    rid = "V001"
    bp = Path(ctx["bactopia_path"])
    try:
        versions = read_versions(bp)
    except (FileNotFoundError, KeyError) as e:
        return [_fail(rid, component, f"versions.yml unreadable: {e}")]

    bactopia_v = versions["bactopia"]
    plugin_v = versions["nf_bactopia"]
    problems: list[str] = []

    def _check(rel: str, pattern: str, expected: str, label: str) -> None:
        path = bp / rel
        if not path.exists():
            return
        m = re.search(pattern, path.read_text(), re.MULTILINE)
        if m and m.group(1) != expected:
            problems.append(f"{label} is '{m.group(1)}', expected '{expected}'")

    _check(
        "nextflow.config",
        r"^\s*version\s*=\s*'([^']+)'",
        bactopia_v,
        "nextflow.config manifest.version",
    )
    _check("bin/bactopia", r"^VERSION=(\S+)", bactopia_v, "bin/bactopia VERSION")
    _check(
        "data/conda/meta.yaml",
        r"set version\s*=\s*'([^']+)'",
        bactopia_v,
        "data/conda/meta.yaml version",
    )
    _check("CITATION.cff", r"^version:\s*(\S+)", bactopia_v, "CITATION.cff version")

    catalog_path = bp / "catalog.json"
    if catalog_path.exists():
        try:
            catalog = json.loads(catalog_path.read_text())
        except json.JSONDecodeError:
            catalog = {}
        cat_v = catalog.get("bactopia_version")
        if cat_v is not None and cat_v != bactopia_v:
            problems.append(
                f"catalog.json bactopia_version is '{cat_v}', expected '{bactopia_v}'"
            )
        cat_nfb = catalog.get("nf_bactopia_version")
        if cat_nfb is not None and cat_nfb != plugin_v:
            problems.append(
                f"catalog.json nf_bactopia_version is '{cat_nfb}', expected '{plugin_v}'"
            )

    # nf-bactopia plugin pins + bactopia_version literals across every *.config
    # (covers workflow configs AND module/subworkflow test configs)
    bad_pins: dict[str, list[str]] = {}
    bad_versions: dict[str, list[str]] = {}
    for cfg in bp.rglob("*.config"):
        if any(part in _SKIP_DIRS for part in cfg.parts):
            continue
        rel = str(cfg.relative_to(bp))
        text = cfg.read_text()
        for m in _PLUGIN_PIN_RE.finditer(text):
            ver = m.group(1)
            if "{" not in ver and ver != plugin_v:
                bad_pins.setdefault(ver, []).append(rel)
        for m in _VERSION_RE.finditer(text):
            ver = m.group(1)
            if "{" not in ver and ver != bactopia_v:
                bad_versions.setdefault(ver, []).append(rel)

    def _summarize(bad: dict[str, list[str]], label: str, expected: str) -> None:
        for ver, files in sorted(bad.items()):
            uniq = sorted(set(files))
            sample = ", ".join(uniq[:5])
            more = "" if len(uniq) <= 5 else f" (+{len(uniq) - 5} more)"
            problems.append(
                f"{label} '{ver}' != versions.yml '{expected}' in: {sample}{more}"
            )

    _summarize(bad_versions, "bactopia_version", bactopia_v)
    _summarize(bad_pins, "nf-bactopia pin", plugin_v)

    if problems:
        return [_fail(rid, component, "; ".join(problems))]
    return [
        _pass(
            rid,
            component,
            f"version-bearing files match versions.yml "
            f"(bactopia={bactopia_v}, nf-bactopia={plugin_v})",
        )
    ]


def rule_v002(component: str, ctx: dict) -> list[LintResult]:
    """Declared pipeline version matches the top CHANGELOG heading.

    versions.yml (bactopia) must equal the version of the top-most CHANGELOG.md
    section; otherwise the repo disagrees with itself about which version is
    being released.
    """
    rid = "V002"
    bp = Path(ctx["bactopia_path"])
    try:
        declared = read_versions(bp)["bactopia"]
    except (FileNotFoundError, KeyError) as e:
        return [_fail(rid, component, f"versions.yml unreadable: {e}")]
    changelog = bp / "CHANGELOG.md"
    if not changelog.exists():
        return [_fail(rid, component, "CHANGELOG.md not found")]
    m = _CHANGELOG_RE.search(changelog.read_text())
    if not m:
        return [_fail(rid, component, "no versioned '## vX.Y.Z' heading in CHANGELOG.md")]
    if m.group(1) != declared:
        return [
            _fail(
                rid,
                component,
                f"CHANGELOG top version '{m.group(1)}' != versions.yml '{declared}'",
            )
        ]
    return [_pass(rid, component, f"CHANGELOG top matches versions.yml ({declared})")]


def rule_v003(component: str, ctx: dict) -> list[LintResult]:
    """Declared nf-bactopia pin is the latest nf-bactopia release.

    Compares versions.yml (nf-bactopia) against the nf-bactopia repo's
    build.gradle version. A lagging pin is a WARN -- it may be intentional, but
    usually means the pipeline hasn't adopted the newest plugin. Skips (PASS)
    when the sibling repo is not checked out beside the bactopia repo.
    """
    rid = "V003"
    bp = Path(ctx["bactopia_path"])
    try:
        declared = read_versions(bp)["nf_bactopia"]
    except (FileNotFoundError, KeyError) as e:
        return [_fail(rid, component, f"versions.yml unreadable: {e}")]
    gradle = bp.parent / "nf-bactopia" / "build.gradle"
    if not gradle.exists():
        return [_pass(rid, component, "nf-bactopia repo not found; cannot verify pin currency")]
    m = _GRADLE_VERSION_RE.search(gradle.read_text())
    if not m:
        return [_pass(rid, component, "no version in nf-bactopia build.gradle")]
    if declared != m.group(1):
        return [
            _warn(
                rid,
                component,
                f"versions.yml nf-bactopia pin '{declared}' lags latest "
                f"nf-bactopia release '{m.group(1)}'",
            )
        ]
    return [_pass(rid, component, f"nf-bactopia pin is current ({declared})")]


REPO_RULES = [rule_v001, rule_v002, rule_v003]
