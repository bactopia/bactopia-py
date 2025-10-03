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
    modules = set()
    if wf not in workflows["workflows"]:
        return list(modules)

    if "includes" in workflows["workflows"][wf]:
        for workflow in workflows["workflows"][wf]["includes"]:
            modules.update(get_modules_by_workflow(workflow, workflows))

    if "modules" in workflows["workflows"][wf]:
        modules.update(workflows["workflows"][wf]["modules"])

    return list(modules)
