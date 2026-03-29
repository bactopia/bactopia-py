"""
Parse the catalog.json produced by bactopia-catalog.
"""


def get_modules_by_workflow(wf: str, catalog: dict) -> list:
    """
    Collect all module keys reachable from a workflow by walking the
    subworkflow graph in catalog.json.

    Args:
        wf: The name of the workflow (e.g., "bactopia", "abricate").
        catalog: The full parsed catalog.json dict.

    Returns:
        A deduplicated list of module keys (e.g., ["abricate_run", "csvtk_concat"]).
    """
    if wf not in catalog["workflows"]:
        return []

    modules = []
    seen_modules = set()
    visited_subworkflows = set()

    def _walk_subworkflow(sw_name: str):
        if sw_name in visited_subworkflows:
            return
        visited_subworkflows.add(sw_name)

        sw = catalog["subworkflows"].get(sw_name)
        if sw is None:
            return

        calls = sw.get("calls", {})

        # Collect modules from this subworkflow
        for mod in calls.get("modules", []):
            if mod not in seen_modules:
                seen_modules.add(mod)
                modules.append(mod)

        # Recurse into nested subworkflows
        for nested_sw in calls.get("subworkflows", []):
            _walk_subworkflow(nested_sw)

    for sw_name in catalog["workflows"][wf].get("subworkflows", []):
        _walk_subworkflow(sw_name)

    return modules
