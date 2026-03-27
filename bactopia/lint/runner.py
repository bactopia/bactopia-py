"""Lint runner: discovers components, builds contexts, and executes rules."""

import re
from pathlib import Path

from bactopia.lint.models import LintResult
from bactopia.lint.rules import MODULE_RULES, SUBWORKFLOW_RULES, WORKFLOW_RULES
from bactopia.nf import (
    find_main_nf,
    parse_groovydoc_full,
    parse_main_nf_structure,
    parse_module_config_full,
    parse_schema_json,
)

# Pattern: // bactopia-lint: ignore RULE1,RULE2  or  // bactopia-lint: ignore RULE1
_IGNORE_PATTERN = re.compile(r"//\s*bactopia-lint:\s*ignore\s+([\w, ]+)")


def _collect_ignores(component_dir: Path) -> set[str]:
    """Scan component files for bactopia-lint ignore directives.

    Looks for comments like: // bactopia-lint: ignore MC009
    or: // bactopia-lint: ignore MC009, JS004
    """
    ignored = set()
    for ext in ("*.nf", "*.config", "*.json"):
        for f in component_dir.glob(ext):
            try:
                text = f.read_text()
            except OSError:
                continue
            for m in _IGNORE_PATTERN.finditer(text):
                for rule_id in m.group(1).split(","):
                    rule_id = rule_id.strip()
                    if rule_id:
                        ignored.add(rule_id)
    return ignored


def _build_module_context(main_nf: Path) -> dict:
    """Build a context dict for a module component."""
    component_dir = main_nf.parent
    return {
        "main_nf_path": main_nf,
        "component_dir": component_dir,
        "groovydoc": parse_groovydoc_full(main_nf),
        "structure": parse_main_nf_structure(main_nf),
        "config": parse_module_config_full(component_dir / "module.config"),
        "schema": parse_schema_json(component_dir / "schema.json"),
    }


def _build_simple_context(main_nf: Path) -> dict:
    """Build a context dict for subworkflow/workflow components (no module.config/schema)."""
    return {
        "main_nf_path": main_nf,
        "component_dir": main_nf.parent,
        "groovydoc": parse_groovydoc_full(main_nf),
        "structure": parse_main_nf_structure(main_nf),
    }


def _run_rules(
    component: str,
    ctx: dict,
    rules: list,
    ignored: set[str] | None = None,
) -> list[LintResult]:
    """Run a list of rule functions against a component context."""
    results = []
    for rule_fn in rules:
        for r in rule_fn(component, ctx):
            if ignored and r.rule_id in ignored and not r.is_pass():
                results.append(
                    LintResult(r.rule_id, "PASS", r.component, f"Ignored: {r.message}")
                )
            else:
                results.append(r)
    return results


def discover_components(
    bactopia_path: Path,
    tier: str,
) -> list[tuple[str, Path]]:
    """Discover components under a tier directory.

    Args:
        bactopia_path: Root path of the Bactopia repo.
        tier: One of "modules", "subworkflows", "workflows".

    Returns:
        List of (component_name, main_nf_path) tuples.
    """
    tier_dir = bactopia_path / tier
    components = []
    for main_nf in find_main_nf(tier_dir):
        rel = main_nf.parent.relative_to(bactopia_path)
        components.append((str(rel), main_nf))
    return components


def run_lint(
    bactopia_path: Path,
    lint_modules: bool = True,
    lint_subworkflows: bool = True,
    lint_workflows: bool = True,
    module_filter: str | None = None,
) -> dict:
    """Run all lint rules against a Bactopia repo.

    Args:
        bactopia_path: Root path of the Bactopia repo.
        lint_modules: Whether to lint modules.
        lint_subworkflows: Whether to lint subworkflows.
        lint_workflows: Whether to lint workflows.
        module_filter: Optional module name filter (e.g. "bakta" or "bakta/run").

    Returns:
        A dict with:
            - results: list of all LintResult objects
            - summary: dict with pass/warn/fail counts
            - components: dict mapping tier names to lists of component results
    """
    all_results: list[LintResult] = []
    components_by_tier: dict[str, list[dict]] = {}

    # Modules
    if lint_modules:
        tier_name = "modules"
        components = discover_components(bactopia_path, tier_name)
        tier_results = []

        for component_name, main_nf in components:
            # Apply module filter
            if module_filter:
                # Match against component name with or without modules/ prefix
                short_name = component_name.replace("modules/", "")
                filter_normalized = module_filter.replace("_", "/")
                if short_name != filter_normalized and not short_name.startswith(
                    f"{filter_normalized}/"
                ):
                    continue

            ctx = _build_module_context(main_nf)
            ignored = _collect_ignores(main_nf.parent)
            results = _run_rules(component_name, ctx, MODULE_RULES, ignored)
            all_results.extend(results)

            # Summarize per-component
            has_fail = any(r.is_fail() for r in results)
            has_warn = any(r.is_warn() for r in results)
            status = "FAIL" if has_fail else "WARN" if has_warn else "PASS"
            tier_results.append(
                {
                    "component": component_name,
                    "status": status,
                    "results": results,
                }
            )

        components_by_tier[tier_name] = tier_results

    # Subworkflows
    if lint_subworkflows and not module_filter:
        tier_name = "subworkflows"
        components = discover_components(bactopia_path, tier_name)
        tier_results = []

        for component_name, main_nf in components:
            ctx = _build_simple_context(main_nf)
            ignored = _collect_ignores(main_nf.parent)
            results = _run_rules(component_name, ctx, SUBWORKFLOW_RULES, ignored)
            all_results.extend(results)

            has_fail = any(r.is_fail() for r in results)
            has_warn = any(r.is_warn() for r in results)
            status = "FAIL" if has_fail else "WARN" if has_warn else "PASS"
            tier_results.append(
                {
                    "component": component_name,
                    "status": status,
                    "results": results,
                }
            )

        components_by_tier[tier_name] = tier_results

    # Workflows
    if lint_workflows and not module_filter:
        tier_name = "workflows"
        components = discover_components(bactopia_path, tier_name)
        tier_results = []

        for component_name, main_nf in components:
            ctx = _build_simple_context(main_nf)
            ignored = _collect_ignores(main_nf.parent)
            results = _run_rules(component_name, ctx, WORKFLOW_RULES, ignored)
            all_results.extend(results)

            has_fail = any(r.is_fail() for r in results)
            has_warn = any(r.is_warn() for r in results)
            status = "FAIL" if has_fail else "WARN" if has_warn else "PASS"
            tier_results.append(
                {
                    "component": component_name,
                    "status": status,
                    "results": results,
                }
            )

        components_by_tier[tier_name] = tier_results

    # Summary
    summary = {
        "pass": sum(1 for r in all_results if r.is_pass()),
        "warn": sum(1 for r in all_results if r.is_warn()),
        "fail": sum(1 for r in all_results if r.is_fail()),
    }

    return {
        "results": all_results,
        "summary": summary,
        "components": components_by_tier,
    }
