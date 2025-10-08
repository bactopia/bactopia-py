"""
Parse the workflows.yml files produced by Bactopia
"""


def get_modules_by_workflow(wf: str, workflows: dict) -> list:
    """
    Recursively get the modules associated with a workflow

    Args:
        wf (str): The name of the workflow
        workflows (dict): The parsed workflows.yml file

    Returns:
        list: A list of modules associated with the workflow
    """
    modules = []
    if wf not in workflows["workflows"]:
        return modules

    if "includes" in workflows["workflows"][wf]:
        for workflow in workflows["workflows"][wf]["includes"]:
            wf_modules = get_modules_by_workflow(workflow, workflows)
            for module in wf_modules:
                if module not in modules:
                    modules.append(module)

    if "modules" in workflows["workflows"][wf]:
        for module in workflows["workflows"][wf]["modules"]:
            if module not in modules:
                modules.append(module)

    return modules
