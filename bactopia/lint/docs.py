"""Reference-doc staleness validation for Bactopia.

Cross-cutting drift checks that don't fit the per-component lint rule
model in ``bactopia.lint.rules``. Two families:

- **D0xx — Deprecated patterns**: phrases retired by past migrations
  (e.g. ``flattenPaths``, the 4-channel emission framing, ``meta: Map``).
  Defined in ``data/docs-patterns.yml`` so new migrations can append
  entries without code changes.
- **D1xx — Ground-truth assertions**: claims about counts, versions,
  CLI commands, lint rule IDs, and file paths that are derivable from
  the live repo.

Inline ignore: append ``<!-- bactopia-docs: ignore D001 -->`` (or a
comma-separated list) to a line to suppress flagged rules on that line.
"""

import logging
import re
from pathlib import Path

import yaml

DEFAULT_DOCS_PATH = ".claude/docs"
DEFAULT_PATTERNS_FILE = "data/docs-patterns.yml"

# Inline suppression: <!-- bactopia-docs: ignore D001, D002 -->
_IGNORE_RE = re.compile(r"<!--\s*bactopia-docs:\s*ignore\s+([A-Z0-9, ]+?)\s*-->")

# Markdown link: [text](path). Captures path in group 2.
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)#?\s]+)(#[^)]*)?\)")

# Lint rule IDs we expect to see referenced in docs.
_RULE_ID_RE = re.compile(r"\b(MC|JS|FMT|M|S|W)(\d{3})\b")

# bactopia-* CLI command names. Only flag inside backticks — references
# in prose are usually directory/repo names (bactopia-tools, bactopia-py)
# or placeholders (bactopia-tool-name), not command invocations.
_CLI_REF_RE = re.compile(r"`(bactopia-[a-z][a-z-]*[a-z0-9])`")

# Count claims: "97 modules", "**Count**: 97 modules", "(70 total".
# Negative lookbehind avoids matching the trailing digit of "1.1 Module"
# (heading number) or "1:1 module wrapper" (ratio).
_COUNT_RE = re.compile(
    r"(?<![\d.:])\b(\d+)\s+(modules?|subworkflows?|workflows?)\b", re.IGNORECASE
)

# Nextflow version mentions: "Nextflow 26.01.0", "Nextflow v25.10".
# Captures the version in group(1) and any trailing "+" / ".x" / ".x+" in
# group(2) — those signal an informational range, not a current claim.
_NEXTFLOW_VERSION_RE = re.compile(
    r"Nextflow[^\d\n]{0,40}?v?(\d+\.\d+(?:\.\d+)?)((?:\.x)?\+?)", re.IGNORECASE
)

# Lines that mention a Nextflow version informationally rather than as a
# current-state claim — feature stabilization notes, "until" markers,
# "natively supported in" phrasing.
_NEXTFLOW_INFORMATIONAL_RE = re.compile(
    r"\b(until|since|stabiliz|natively\s+supported|introduces|earlier\s+than|"
    r"later\s+than|preview|deprecated\s+in|removed\s+in)\b",
    re.IGNORECASE,
)

# nextflow.config: nextflowVersion = '>=25.04.6'
_NEXTFLOW_CONFIG_RE = re.compile(
    r"nextflowVersion\s*=\s*['\"][^\d]*(\d+\.\d+(?:\.\d+)?)"
)

# Skill table row in .claude/docs/reference/06-skills.md. Anchors on the
# first column being a markdown link whose target ends with "skills/<name>"
# where <name> matches the link text — keeps the rule scoped to the
# intended table and ignores unrelated tables in the same doc.
# Groups: (1)=name, (2)=link target, (3)=backend cell, (4)=purpose cell.
_SKILL_ROW_RE = re.compile(
    r"^\s*\|\s*\[([a-z0-9][a-z0-9-]*)\]\(([^)]*skills/\1/?)\)"
    r"\s*\|\s*([^|]*?)\s*\|\s*(.+?)\s*\|\s*$"
)

# Relative path (within docs_path) of the skills reference doc D107 checks.
_SKILLS_DOC_REL = "reference/06-skills.md"


# ---------- pattern registry loader ----------


def _load_patterns(patterns_file: Path) -> list[dict]:
    """Load the deprecated-pattern registry.

    Each entry yields a dict with id, pattern (compiled), severity, hint,
    and the original literal/regex text for diagnostics.

    YAML schema (per entry)::

        - id: D001
          pattern: flattenPaths
          literal: true   # optional; if true, escape pattern as plain text
          severity: FAIL  # PASS | WARN | FAIL (default FAIL)
          hint: "Function removed; remove or rephrase."
          rationale: "Retired during nf-bactopia 2.0 cleanup."
    """
    try:
        with open(patterns_file) as f:
            data = yaml.safe_load(f)
    except OSError as e:
        logging.debug("Could not read %s: %s", patterns_file, e)
        return []
    except yaml.YAMLError as e:
        logging.debug("Invalid YAML in %s: %s", patterns_file, e)
        return []

    if not data or "patterns" not in data:
        return []

    compiled: list[dict] = []
    for entry in data["patterns"]:
        raw = entry.get("pattern")
        if not raw:
            continue
        text = re.escape(raw) if entry.get("literal") else raw
        try:
            regex = re.compile(text)
        except re.error as e:
            logging.warning(
                "Skipping pattern %s: invalid regex (%s)", entry.get("id"), e
            )
            continue
        compiled.append(
            {
                "id": entry["id"],
                "regex": regex,
                "raw": raw,
                "severity": entry.get("severity", "FAIL"),
                "hint": entry.get("hint", ""),
                "rationale": entry.get("rationale", ""),
            }
        )
    return compiled


# ---------- doc enumeration ----------


def _iter_doc_files(docs_dir: Path) -> list[Path]:
    """Return sorted list of .md files under docs_dir."""
    if not docs_dir.is_dir():
        return []
    return sorted(docs_dir.rglob("*.md"))


def _ignored_rules(line: str) -> set[str]:
    """Return the set of rule IDs suppressed on this line."""
    m = _IGNORE_RE.search(line)
    if not m:
        return set()
    return {token.strip() for token in m.group(1).split(",") if token.strip()}


# ---------- D0xx: deprecated pattern check ----------


def _check_deprecated_patterns(
    file_rel: str, lines: list[str], patterns: list[dict]
) -> list[dict]:
    """Grep each line against each compiled pattern."""
    hits: list[dict] = []
    for idx, line in enumerate(lines, start=1):
        suppressed = _ignored_rules(line)
        for pat in patterns:
            if pat["id"] in suppressed:
                continue
            m = pat["regex"].search(line)
            if not m:
                continue
            hits.append(
                {
                    "rule_id": pat["id"],
                    "severity": pat["severity"],
                    "file": file_rel,
                    "line": idx,
                    "match": line.strip()[:160],
                    "pattern": pat["raw"],
                    "hint": pat["hint"],
                }
            )
    return hits


# ---------- D1xx: ground-truth assertions ----------


def _compute_counts(bactopia_path: Path) -> dict:
    """Count main.nf files in each tier; workflows includes the root one."""
    counts = {
        "modules": len(list((bactopia_path / "modules").rglob("main.nf"))),
        "subworkflows": len(list((bactopia_path / "subworkflows").rglob("main.nf"))),
    }
    workflow_count = len(list((bactopia_path / "workflows").rglob("main.nf")))
    if (bactopia_path / "main.nf").is_file():
        workflow_count += 1
    counts["workflows"] = workflow_count
    return counts


def _compute_nextflow_version(bactopia_path: Path) -> str | None:
    """Extract the manifest nextflowVersion from nextflow.config."""
    cfg = bactopia_path / "nextflow.config"
    if not cfg.is_file():
        return None
    try:
        text = cfg.read_text()
    except OSError:
        return None
    m = _NEXTFLOW_CONFIG_RE.search(text)
    return m.group(1) if m else None


def _compute_cli_commands(bactopia_py_path: Path) -> set[str]:
    """Parse the [tool.poetry.scripts] block for command names."""
    pyproject = bactopia_py_path / "pyproject.toml"
    if not pyproject.is_file():
        return set()
    try:
        text = pyproject.read_text()
    except OSError:
        return set()
    commands: set[str] = set()
    in_scripts = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[tool.poetry.scripts]"):
            in_scripts = True
            continue
        if (
            in_scripts
            and stripped.startswith("[")
            and not stripped.startswith("[tool.poetry.scripts]")
        ):
            break
        if in_scripts and "=" in stripped and not stripped.startswith("#"):
            name = stripped.split("=", 1)[0].strip()
            if name.startswith("bactopia-"):
                commands.add(name)
    return commands


def _compute_lint_rule_ids(bactopia_py_path: Path) -> set[str]:
    """Scan lint/rules/*.py for rid = "<ID>" assignments."""
    rules_dir = bactopia_py_path / "bactopia" / "lint" / "rules"
    if not rules_dir.is_dir():
        return set()
    ids: set[str] = set()
    rid_re = re.compile(r"""rid\s*=\s*["']([A-Z]+\d{3})["']""")
    for py in rules_dir.glob("*.py"):
        try:
            for m in rid_re.finditer(py.read_text()):
                ids.add(m.group(1))
        except OSError:
            continue
    return ids


def _first_sentence(text: str) -> str:
    """Return text up through the first '. ' terminator, or full text."""
    text = text.strip()
    m = re.search(r"\.\s+", text)
    return text[: m.start() + 1] if m else text


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace for loose string comparison."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _compute_skills(bactopia_path: Path) -> dict[str, dict]:
    """Scan ``.claude/skills/*/SKILL.md`` and extract frontmatter descriptions.

    Returns a mapping of ``skill_name -> {description, first_sentence}``.
    Skills without frontmatter or without a ``description`` field still
    appear (inventory symmetry is checkable regardless); ``first_sentence``
    is empty in that case and description-drift checks are skipped for them.
    """
    skills_dir = bactopia_path / ".claude" / "skills"
    if not skills_dir.is_dir():
        return {}
    skills: dict[str, dict] = {}
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        name = skill_md.parent.name
        try:
            text = skill_md.read_text()
        except OSError:
            continue
        if not text.startswith("---"):
            skills[name] = {"description": "", "first_sentence": ""}
            continue
        end = text.find("\n---", 3)
        if end < 0:
            skills[name] = {"description": "", "first_sentence": ""}
            continue
        try:
            fm = yaml.safe_load(text[3:end]) or {}
        except yaml.YAMLError:
            skills[name] = {"description": "", "first_sentence": ""}
            continue
        desc = str(fm.get("description", "")).strip()
        skills[name] = {
            "description": desc,
            "first_sentence": _first_sentence(desc),
        }
    return skills


def _check_skill_inventory(
    file_rel: str,
    doc_path: Path,
    skills: dict[str, dict],
) -> list[dict]:
    """D107: cross-check ``06-skills.md`` against ``.claude/skills/*/SKILL.md``.

    Three failure modes:
    - Skill exists under ``.claude/skills/`` but isn't listed in the table.
    - Skill listed in the table has no matching directory.
    - Purpose cell drifted from the ``description:`` first sentence.

    Skips silently when ``skills`` is empty (no skills on disk) or the
    doc itself is missing — same pattern as D105/D106 when bactopia-py
    isn't found.
    """
    if not skills or not doc_path.is_file():
        return []
    try:
        lines = doc_path.read_text().splitlines()
    except OSError:
        return []

    hits: list[dict] = []
    listed: dict[str, tuple[int, str]] = {}

    for idx, line in enumerate(lines, start=1):
        if "D107" in _ignored_rules(line):
            continue
        m = _SKILL_ROW_RE.match(line)
        if not m:
            continue
        name = m.group(1)
        purpose = m.group(4).strip()
        if name in listed:
            hits.append(
                {
                    "rule_id": "D107",
                    "severity": "FAIL",
                    "file": file_rel,
                    "line": idx,
                    "match": line.strip()[:160],
                    "reference": name,
                    "hint": f"Skill '{name}' listed more than once.",
                }
            )
            continue
        listed[name] = (idx, purpose)

    fs_names = set(skills.keys())
    listed_names = set(listed.keys())

    for name in sorted(fs_names - listed_names):
        hits.append(
            {
                "rule_id": "D107",
                "severity": "FAIL",
                "file": file_rel,
                "line": 0,
                "match": "",
                "reference": name,
                "hint": (
                    f"Skill '{name}' exists under .claude/skills/ but is not "
                    "listed in the table."
                ),
            }
        )

    for name in sorted(listed_names - fs_names):
        line_num, _ = listed[name]
        hits.append(
            {
                "rule_id": "D107",
                "severity": "FAIL",
                "file": file_rel,
                "line": line_num,
                "match": "",
                "reference": name,
                "hint": (
                    f"Skill '{name}' listed in table but no "
                    f".claude/skills/{name}/ directory exists."
                ),
            }
        )

    for name in sorted(fs_names & listed_names):
        expected = skills[name]["first_sentence"]
        if not expected:
            continue
        line_num, purpose = listed[name]
        if _normalize(purpose) == _normalize(expected):
            continue
        hits.append(
            {
                "rule_id": "D107",
                "severity": "FAIL",
                "file": file_rel,
                "line": line_num,
                "match": purpose[:160],
                "reference": name,
                "claim": purpose,
                "actual": expected,
                "hint": (f"Purpose drifted from SKILL.md description for '{name}'."),
            }
        )

    return hits


def _check_count_claims(file_rel: str, lines: list[str], counts: dict) -> list[dict]:
    """Flag '<N> modules/subworkflows/workflows' that disagree with counts."""
    rule_map = {"modules": "D101", "subworkflows": "D102", "workflows": "D103"}
    hits: list[dict] = []
    for idx, line in enumerate(lines, start=1):
        suppressed = _ignored_rules(line)
        for m in _COUNT_RE.finditer(line):
            claimed = int(m.group(1))
            tier = m.group(2).lower().rstrip("s") + "s"  # normalize plural
            rule_id = rule_map[tier]
            if rule_id in suppressed:
                continue
            actual = counts.get(tier)
            if actual is None or claimed == actual:
                continue
            hits.append(
                {
                    "rule_id": rule_id,
                    "severity": "FAIL",
                    "file": file_rel,
                    "line": idx,
                    "match": line.strip()[:160],
                    "claim": f"{claimed} {tier}",
                    "actual": f"{actual} {tier}",
                }
            )
    return hits


def _check_version_claims(
    file_rel: str, lines: list[str], nextflow_version: str | None
) -> list[dict]:
    """Flag 'Nextflow vX.Y.Z' claims that don't match nextflow.config."""
    if not nextflow_version:
        return []
    hits: list[dict] = []
    for idx, line in enumerate(lines, start=1):
        if "D104" in _ignored_rules(line):
            continue
        m = _NEXTFLOW_VERSION_RE.search(line)
        if not m:
            continue
        claimed = m.group(1)
        suffix = m.group(2) or ""
        if claimed == nextflow_version:
            continue
        # Skip informational mentions: "<version>+", "<version>.x[+]",
        # or lines with feature-stabilization phrasing.
        if suffix or _NEXTFLOW_INFORMATIONAL_RE.search(line):
            continue
        # Allow major.minor matches when actual has a patch (e.g. claim
        # "26.04" vs actual "26.04.6"). Strict if both are full versions.
        actual_major_minor = ".".join(nextflow_version.split(".")[:2])
        if claimed == actual_major_minor:
            continue
        hits.append(
            {
                "rule_id": "D104",
                "severity": "FAIL",
                "file": file_rel,
                "line": idx,
                "match": line.strip()[:160],
                "claim": f"Nextflow {claimed}",
                "actual": f"Nextflow {nextflow_version}",
            }
        )
    return hits


def _check_cli_references(
    file_rel: str, lines: list[str], valid_cmds: set[str]
) -> list[dict]:
    """Flag bactopia-* references that don't resolve to a known command."""
    if not valid_cmds:
        return []
    hits: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for idx, line in enumerate(lines, start=1):
        if "D105" in _ignored_rules(line):
            continue
        for m in _CLI_REF_RE.finditer(line):
            cmd = m.group(1)
            if cmd in valid_cmds:
                continue
            sig = (idx, cmd)
            if sig in seen:
                continue
            seen.add(sig)
            hits.append(
                {
                    "rule_id": "D105",
                    "severity": "FAIL",
                    "file": file_rel,
                    "line": idx,
                    "match": line.strip()[:160],
                    "reference": cmd,
                    "hint": "Command not found in bactopia-py [tool.poetry.scripts].",
                }
            )
    return hits


def _check_rule_id_references(
    file_rel: str, lines: list[str], valid_ids: set[str]
) -> list[dict]:
    """Flag M0xx/S0xx/W0xx etc. references that don't resolve to a real rule."""
    if not valid_ids:
        return []
    hits: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for idx, line in enumerate(lines, start=1):
        if "D106" in _ignored_rules(line):
            continue
        for m in _RULE_ID_RE.finditer(line):
            rid = m.group(1) + m.group(2)
            if rid in valid_ids:
                continue
            sig = (idx, rid)
            if sig in seen:
                continue
            seen.add(sig)
            hits.append(
                {
                    "rule_id": "D106",
                    "severity": "FAIL",
                    "file": file_rel,
                    "line": idx,
                    "match": line.strip()[:160],
                    "reference": rid,
                    "hint": "Rule ID not found in bactopia-py/bactopia/lint/rules/.",
                }
            )
    return hits


def _check_path_references(
    file_rel: str,
    file_path: Path,
    lines: list[str],
    bactopia_path: Path,
) -> list[dict]:
    """Flag markdown link targets that don't resolve to a real path.

    Only checks links that look like local repo paths:
    - Skips http/https URLs.
    - Skips anchor-only links (``#section``).
    - Skips mailto: and similar schemes.
    - Resolves relative to the doc's parent directory; if that fails,
      retries relative to bactopia_path.
    """
    hits: list[dict] = []
    seen: set[tuple[int, str]] = set()
    doc_dir = file_path.parent
    for idx, line in enumerate(lines, start=1):
        if "D108" in _ignored_rules(line):
            continue
        for m in _LINK_RE.finditer(line):
            target = m.group(2).strip()
            if not target:
                continue
            if target.startswith(("http://", "https://", "mailto:", "ftp://", "//")):
                continue
            if target.startswith("#"):
                continue
            if ":" in target and not target.startswith((".", "/")):
                # likely a scheme we don't handle
                continue
            # Skip bare-word placeholders like `[link](url)` or
            # `[ToolName](URL)` that appear in template examples — a real
            # path always has either a separator or a file extension.
            if "/" not in target and "." not in target:
                continue

            # Try doc-relative first, then repo-relative.
            candidate = (doc_dir / target).resolve()
            if candidate.exists():
                continue
            alt = (bactopia_path / target.lstrip("/")).resolve()
            if alt.exists():
                continue

            sig = (idx, target)
            if sig in seen:
                continue
            seen.add(sig)
            hits.append(
                {
                    "rule_id": "D108",
                    "severity": "FAIL",
                    "file": file_rel,
                    "line": idx,
                    "match": line.strip()[:160],
                    "reference": target,
                    "hint": "Markdown link target does not resolve.",
                }
            )
    return hits


# ---------- top-level entry ----------


def _resolve_sibling(
    bactopia_path: Path, name: str, override: Path | None
) -> Path | None:
    """Return override if provided, else the sibling repo if it exists."""
    if override:
        return override if override.is_dir() else None
    sibling = bactopia_path.parent / name
    return sibling if sibling.is_dir() else None


def validate_docs(
    bactopia_path: Path,
    docs_path: str = DEFAULT_DOCS_PATH,
    patterns_file: str = DEFAULT_PATTERNS_FILE,
    bactopia_py_path: Path | None = None,
    skip_path_check: bool = False,
) -> dict:
    """Validate reference-doc staleness across a Bactopia repo.

    Args:
        bactopia_path: Root path of the Bactopia repo.
        docs_path: Docs directory relative to bactopia_path.
        patterns_file: Deprecated-patterns YAML, relative to bactopia_path.
        bactopia_py_path: Path to the bactopia-py repo for D105/D106 checks.
            Defaults to ``<bactopia_path>/../bactopia-py``; checks are skipped
            with a warning if neither override nor sibling resolves.
        skip_path_check: If True, skip the D108 link-target check (useful
            for fast runs).

    Returns:
        A dict with the following shape::

            {
                "bactopia_path": str,
                "docs_path": str,
                "patterns_file": str,
                "ground_truth": {
                    "counts": {modules, subworkflows, workflows},
                    "nextflow_version": str | None,
                    "cli_commands_total": int,
                    "lint_rule_ids_total": int,
                },
                "files_scanned": [str, ...],
                "deprecated_patterns": [dict, ...],
                "ground_truth_violations": [dict, ...],
                "summary": {
                    "files_scanned": int,
                    "deprecated_pattern_hits": int,
                    "ground_truth_violations": int,
                    "fail": int,
                    "warn": int,
                    "pass": int,
                },
            }

    Inline ``<!-- bactopia-docs: ignore D0xx -->`` HTML comments suppress
    a rule on the line they appear in. Use this sparingly for intentional
    historical references (e.g. a glossary entry that names a deprecated
    term to explain its replacement).
    """
    docs_dir = bactopia_path / docs_path
    patterns_path = bactopia_path / patterns_file

    patterns = _load_patterns(patterns_path)
    counts = _compute_counts(bactopia_path)
    nextflow_version = _compute_nextflow_version(bactopia_path)

    bactopia_py = _resolve_sibling(bactopia_path, "bactopia-py", bactopia_py_path)
    valid_cmds = _compute_cli_commands(bactopia_py) if bactopia_py else set()
    valid_rule_ids = _compute_lint_rule_ids(bactopia_py) if bactopia_py else set()
    skills = _compute_skills(bactopia_path)

    docs = _iter_doc_files(docs_dir)
    files_scanned: list[str] = []
    deprecated_hits: list[dict] = []
    ground_truth_hits: list[dict] = []

    for doc in docs:
        rel = str(doc.relative_to(docs_dir))
        files_scanned.append(rel)
        try:
            text = doc.read_text()
        except OSError:
            continue
        lines = text.splitlines()

        deprecated_hits.extend(_check_deprecated_patterns(rel, lines, patterns))
        ground_truth_hits.extend(_check_count_claims(rel, lines, counts))
        ground_truth_hits.extend(_check_version_claims(rel, lines, nextflow_version))
        ground_truth_hits.extend(_check_cli_references(rel, lines, valid_cmds))
        ground_truth_hits.extend(_check_rule_id_references(rel, lines, valid_rule_ids))
        if rel == _SKILLS_DOC_REL:
            ground_truth_hits.extend(_check_skill_inventory(rel, doc, skills))
        if not skip_path_check:
            ground_truth_hits.extend(
                _check_path_references(rel, doc, lines, bactopia_path)
            )

    fail = sum(
        1 for h in deprecated_hits + ground_truth_hits if h["severity"] == "FAIL"
    )
    warn = sum(
        1 for h in deprecated_hits + ground_truth_hits if h["severity"] == "WARN"
    )
    return {
        "bactopia_path": str(bactopia_path),
        "docs_path": docs_path,
        "patterns_file": patterns_file,
        "ground_truth": {
            "counts": counts,
            "nextflow_version": nextflow_version,
            "cli_commands_total": len(valid_cmds),
            "lint_rule_ids_total": len(valid_rule_ids),
            "skills_count": len(skills),
            "bactopia_py_resolved": str(bactopia_py) if bactopia_py else None,
        },
        "files_scanned": files_scanned,
        "deprecated_patterns": deprecated_hits,
        "ground_truth_violations": ground_truth_hits,
        "summary": {
            "files_scanned": len(files_scanned),
            "deprecated_pattern_hits": len(deprecated_hits),
            "ground_truth_violations": len(ground_truth_hits),
            "fail": fail,
            "warn": warn,
            "pass": 1 if fail == 0 and warn == 0 else 0,
            "patterns_loaded": len(patterns),
        },
    }
