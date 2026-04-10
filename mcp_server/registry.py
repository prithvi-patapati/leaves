from employees.tools.employee_mgmt_tools import EMPLOYEE_MGMT_TOOLS
from employees.tools.org_tools import ORG_TOOLS
from employees.tools.hr_action_tools import HR_ACTION_TOOLS
from leaves.tools.employee_tools import EMPLOYEE_TOOLS
from leaves.tools.manager_tools import MANAGER_TOOLS
from leaves.tools.admin_tools import ADMIN_TOOLS

ALL_TOOLS = (
    EMPLOYEE_MGMT_TOOLS + ORG_TOOLS + HR_ACTION_TOOLS +
    EMPLOYEE_TOOLS + MANAGER_TOOLS + ADMIN_TOOLS
)

ROLE_TOOLS = {
    'EMPLOYEE': EMPLOYEE_TOOLS,
    'MANAGER': EMPLOYEE_TOOLS + MANAGER_TOOLS,
    'ADMIN': ALL_TOOLS,
}


def get_tools_for_role(role):
    return ROLE_TOOLS.get(role, EMPLOYEE_TOOLS)


def get_tool_by_name(name):
    for tool in ALL_TOOLS:
        if tool['name'] == name:
            return tool
    return None


def list_tool_schemas(role='ADMIN'):
    tools = get_tools_for_role(role)
    return [
        {
            'name': t['name'],
            'description': t['description'],
            'input_schema': t['input_schema'],
        }
        for t in tools
    ]
