"""Citation integrity validation for Bactopia.

Cross-cutting citation checks that don't fit the per-component lint rule
model in ``bactopia.lint.rules``:

- **Orphan keys**: entries defined in ``data/citations.yml`` that are never
  referenced by an ``@citation`` tag in any module, subworkflow, or workflow.
- **Missing workflow keys**: ``@citation`` entries in workflow ``main.nf``
  files that reference keys not present in ``citations.yml``. Per-component
  validation of module and subworkflow references is handled by lint rules
  M035 and S019, so this function focuses on the workflow-tier gap and the
  cross-cutting orphan scan.
"""

import logging
import re
from pathlib import Path

import yaml

from bactopia.nf import find_main_nf, parse_groovydoc_full

# Matches the opening line of a GroovyDoc ``* @citation ...`` tag. Used to
# recover 1-based line numbers for reporting; the GroovyDoc parser itself
# discards line offsets.
_CITATION_LINE_RE = re.compile(r"^\s*\*\s*@citation\b\s*(.*)$")

TIERS = ("modules", "subworkflows", "workflows")


def _load_citations_grouped(citations_yml: Path) -> dict:
    """Load citations.yml preserving the top-level grouping.

    Args:
        citations_yml: Path to ``data/citations.yml``.

    Returns:
        Dict mapping section name -> dict of key -> entry. Empty dict on
        missing file or parse error (callers will see no keys rather than
        crash, matching the tolerant behaviour of ``_load_citation_keys``
        in the lint runner).
    """
    try:
        with open(citations_yml) as f:
            data = yaml.safe_load(f)
        return data or {}
    except OSError as e:
        logging.debug("Could not read %s: %s", citations_yml, e)
        return {}
    except yaml.YAMLError as e:
        logging.debug("Invalid YAML in %s: %s", citations_yml, e)
        return {}


def _all_keys(grouped: dict) -> set[str]:
    """Flatten a grouped citations dict to a set of lowercase keys."""
    keys: set[str] = set()
    for entries in grouped.values():
        if isinstance(entries, dict):
            keys.update(k.lower() for k in entries.keys())
    return keys


def _provenance_only_keys(grouped: dict) -> set[str]:
    """Return lowercase keys whose entry carries ``provenance_only: true``.

    These entries are deliberately unreferenced — foundational tools or
    frameworks acknowledged in the citations page but not tied to any
    individual pipeline component (e.g. nextflow, nf-core, nf-test).
    Orphan detection splits them into an ``expected_orphans`` bucket so
    they don't trip the validator.
    """
    marked: set[str] = set()
    for entries in grouped.values():
        if not isinstance(entries, dict):
            continue
        for key, entry in entries.items():
            if isinstance(entry, dict) and entry.get("provenance_only") is True:
                marked.add(key.lower())
    return marked


def _split_citation_value(value: str) -> list[str]:
    """Split a ``@citation a, b, c`` value into lowercase keys."""
    if not value:
        return []
    return [k.strip().lower() for k in value.split(",") if k.strip()]


def _collect_tier_references(
    bactopia_path: Path, tier: str
) -> list[tuple[str, Path, list[str]]]:
    """Walk a tier directory and collect @citation keys per component."""
    tier_dir = bactopia_path / tier
    results: list[tuple[str, Path, list[str]]] = []
    for main_nf in find_main_nf(tier_dir):
        doc = parse_groovydoc_full(main_nf)
        if not doc["has_doc"]:
            continue
        keys = _split_citation_value(doc["tags"].get("citation", ""))
        component = str(main_nf.parent.relative_to(bactopia_path))
        results.append((component, main_nf, keys))
    return results


def _citation_line_number(main_nf: Path, key: str) -> int | None:
    """Return the 1-based line number of the @citation line containing key."""
    try:
        lines = main_nf.read_text().splitlines()
    except OSError:
        return None
    for idx, line in enumerate(lines, start=1):
        m = _CITATION_LINE_RE.match(line)
        if not m:
            continue
        entry_keys = [k.strip().lower() for k in m.group(1).split(",")]
        if key in entry_keys:
            return idx
    return None


def _key_variants(key: str) -> set[str]:
    """Return lowercase surface forms a yml key might appear in filesystem paths
    or config strings.

    yml keys use underscore-separated lowercase (``cd_hit_est``,
    ``maskrc_svg``). The actual tools usually publish under hyphenated or
    concatenated names (``cd-hit-est``, ``maskrc-svg``, ``cdhit``). Matching
    needs all three forms.
    """
    key = key.lower()
    return {key, key.replace("_", "-"), key.replace("_", "")}


def _sibling_key(orphan: str, yml_keys: set[str], referenced: set[str]) -> str | None:
    """Return the closest yml key that is actually referenced, if any.

    Used to flag duplicate/superseded pairs like ``cdhit`` ↔ ``cd_hit_est``,
    ``mash_screen`` ↔ ``mash``, ``btyper2`` ↔ ``btyper3``. Only returns a hit
    when the sibling is referenced — an unreferenced sibling isn't useful
    triage signal.
    """
    orphan = orphan.lower()
    candidates: list[str] = []
    for other in yml_keys:
        if other == orphan or other not in referenced:
            continue
        if other in orphan or orphan in other:
            candidates.append(other)
            continue
        # Prefix/suffix strip: btyper2 vs btyper3, spatyper vs spatyper_db
        ostrip = orphan.rstrip("0123456789")
        cstrip = other.rstrip("0123456789")
        if ostrip and ostrip == cstrip:
            candidates.append(other)
    if not candidates:
        return None
    # Prefer the shortest match (most likely the canonical form).
    return min(candidates, key=len)


def _suggest_homes(
    orphans: dict[str, list[str]],
    bactopia_path: Path,
    yml_keys: set[str],
    referenced: set[str],
) -> dict[str, list[dict]]:
    """Suggest candidate homes for each orphan key.

    Runs five heuristics, each producing ``{type, path, hint}`` candidates:

    1. ``directory`` — ``modules/<key>/`` or nested equivalent exists.
    2. ``toolName`` — ``bioconda::<key>`` or ``<key>-`` appears in a
       ``module.config`` ext.toolName string.
    3. ``config_param`` — orphan key appears as a config value in
       ``module.config`` (e.g. ``panaroo_aligner = 'mafft'``).
    4. ``script_token`` — orphan key appears as a whitespace-delimited
       token inside a ``main.nf`` script block (e.g. ``mash screen``).
    5. ``sibling_key`` — another yml key is a close variant AND is
       actually referenced (duplicate/superseded flag).

    Returns:
        Mapping of orphan key → candidate list. Keys with no candidates
        are omitted. Called only with the filtered orphan set (after
        ``expected_orphans`` split) — no point suggesting homes for
        intentional provenance entries.
    """
    flat_orphans: list[str] = sorted(
        {k.lower() for keys in orphans.values() for k in keys}
    )
    if not flat_orphans:
        return {}

    variant_map: dict[str, set[str]] = {k: _key_variants(k) for k in flat_orphans}
    candidates: dict[str, list[dict]] = {k: [] for k in flat_orphans}

    # Heuristic 1: directory match under modules/ and subworkflows/.
    for tier in ("modules", "subworkflows"):
        tier_dir = bactopia_path / tier
        if not tier_dir.is_dir():
            continue
        for sub in tier_dir.rglob("*"):
            if not sub.is_dir():
                continue
            name = sub.name.lower()
            for orphan in flat_orphans:
                if name in variant_map[orphan]:
                    candidates[orphan].append(
                        {
                            "type": "directory",
                            "path": str(sub.relative_to(bactopia_path)) + "/",
                            "hint": f"directory name '{sub.name}' matches orphan",
                        }
                    )

    # Heuristics 2 + 3: walk module.config files once, scan for each orphan.
    for cfg in bactopia_path.glob("modules/**/module.config"):
        try:
            text = cfg.read_text()
        except OSError:
            continue
        lines = text.splitlines()
        for orphan in flat_orphans:
            variants = variant_map[orphan]
            for idx, line in enumerate(lines, start=1):
                lowered = line.lower()
                for v in variants:
                    if not v:
                        continue
                    if v in lowered:
                        # Classify toolName vs other config by context in the line.
                        if "toolname" in lowered or "bioconda::" in lowered:
                            kind = "toolName"
                            hint = line.strip()
                        else:
                            kind = "config_param"
                            hint = line.strip()
                        candidates[orphan].append(
                            {
                                "type": kind,
                                "path": f"{cfg.relative_to(bactopia_path)}:{idx}",
                                "hint": hint[:120],
                            }
                        )
                        break  # one hit per line is enough

    # Heuristic 4: walk main.nf script-block regions for orphan-as-token.
    for tier in TIERS:
        tier_dir = bactopia_path / tier
        if not tier_dir.is_dir():
            continue
        for main_nf in find_main_nf(tier_dir):
            try:
                lines = main_nf.read_text().splitlines()
            except OSError:
                continue
            in_script = False
            for idx, line in enumerate(lines, start=1):
                stripped = line.strip()
                if stripped.startswith("script:"):
                    in_script = True
                    continue
                if in_script and stripped.startswith("}"):
                    in_script = False
                if not in_script:
                    continue
                lowered = line.lower()
                for orphan in flat_orphans:
                    for v in variant_map[orphan]:
                        if not v:
                            continue
                        # Require a word-like boundary to avoid e.g. "vt" matching "virulent".
                        pattern = rf"(^|[^a-z0-9_-]){re.escape(v)}($|[^a-z0-9_-])"
                        if re.search(pattern, lowered):
                            candidates[orphan].append(
                                {
                                    "type": "script_token",
                                    "path": f"{main_nf.relative_to(bactopia_path)}:{idx}",
                                    "hint": stripped[:120],
                                }
                            )
                            break

    # Heuristic 5: sibling key flag.
    for orphan in flat_orphans:
        sibling = _sibling_key(orphan, yml_keys, referenced)
        if sibling:
            candidates[orphan].append(
                {
                    "type": "sibling_key",
                    "path": f"data/citations.yml ({sibling})",
                    "hint": f"possible duplicate/variant of referenced key '{sibling}'",
                }
            )

    # Drop orphans with no candidates and de-duplicate candidate rows per key.
    result: dict[str, list[dict]] = {}
    for orphan, items in candidates.items():
        if not items:
            continue
        seen: set[tuple[str, str]] = set()
        deduped: list[dict] = []
        for item in items:
            sig = (item["type"], item["path"])
            if sig in seen:
                continue
            seen.add(sig)
            deduped.append(item)
        result[orphan] = deduped
    return result


def validate_citations(bactopia_path: Path) -> dict:
    """Validate citation integrity across a Bactopia repo.

    Complements the per-component lint rules (M035, S019) with two checks
    that require a full-repo view:

    1. Orphan detection: every key in ``data/citations.yml`` is expected to
       be cited somewhere; unreferenced keys accumulate as tools are
       replaced or renamed.
    2. Workflow ``@citation`` validation: no equivalent of M035/S019 exists
       in the W-series today, so a workflow can reference a nonexistent
       key without triggering a lint FAIL.

    Args:
        bactopia_path: Root path of the Bactopia repo.

    Returns:
        A dict with the following shape::

            {
                "orphans": {<section>: [<key>, ...], ...},
                "expected_orphans": {<section>: [<key>, ...], ...},
                "potential_homes": {
                    "<orphan_key>": [
                        {"type": str, "path": str, "hint": str},
                        ...
                    ],
                    ...
                },
                "missing_workflow_keys": [
                    {"component": str, "file": str, "line": int|None, "key": str},
                    ...
                ],
                "summary": {
                    "orphans_total": int,
                    "expected_orphans_total": int,
                    "missing_total": int,
                    "yml_total": int,
                    "referenced_total": int,
                },
            }

    Entries in ``citations.yml`` that declare ``provenance_only: true`` are
    split out of ``orphans`` into ``expected_orphans`` — they're intentionally
    unreferenced (foundational tools acknowledged for provenance only) and
    should not trigger a non-zero exit code.

    ``potential_homes`` runs heuristic matches against repo state (directory
    names, ``module.config`` toolNames, script-block tokens, sibling yml
    keys) to help triage real orphans; only entries in ``orphans`` appear
    here, never ``expected_orphans``.
    """
    citations_yml = bactopia_path / "data" / "citations.yml"
    grouped = _load_citations_grouped(citations_yml)
    yml_keys = _all_keys(grouped)
    provenance_only = _provenance_only_keys(grouped)

    referenced: set[str] = set()
    per_tier: dict[str, list[tuple[str, Path, list[str]]]] = {}
    for tier in TIERS:
        tier_refs = _collect_tier_references(bactopia_path, tier)
        per_tier[tier] = tier_refs
        for _, _, keys in tier_refs:
            referenced.update(keys)

    orphans: dict[str, list[str]] = {}
    expected_orphans: dict[str, list[str]] = {}
    for section, entries in grouped.items():
        if not isinstance(entries, dict):
            continue
        section_orphans: list[str] = []
        section_expected: list[str] = []
        for key in entries.keys():
            if key.lower() in referenced:
                continue
            if key.lower() in provenance_only:
                section_expected.append(key)
            else:
                section_orphans.append(key)
        orphans[section] = sorted(section_orphans)
        expected_orphans[section] = sorted(section_expected)

    missing: list[dict] = []
    for component, main_nf, keys in per_tier["workflows"]:
        for key in keys:
            if key in yml_keys:
                continue
            missing.append(
                {
                    "component": component,
                    "file": str(main_nf.relative_to(bactopia_path)),
                    "line": _citation_line_number(main_nf, key),
                    "key": key,
                }
            )

    orphans_total = sum(len(v) for v in orphans.values())
    expected_orphans_total = sum(len(v) for v in expected_orphans.values())
    potential_homes = _suggest_homes(orphans, bactopia_path, yml_keys, referenced)
    return {
        "orphans": orphans,
        "expected_orphans": expected_orphans,
        "potential_homes": potential_homes,
        "missing_workflow_keys": missing,
        "summary": {
            "orphans_total": orphans_total,
            "expected_orphans_total": expected_orphans_total,
            "missing_total": len(missing),
            "yml_total": len(yml_keys),
            "referenced_total": len(referenced),
        },
    }
