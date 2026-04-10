ORG_TOOLS = [
    {
        "name": "create_department",
        "description": "Create a new department.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "code": {"type": "string"},
                "description": {"type": "string"}
            },
            "required": ["name", "code"]
        },
        "handler": "employees.services.org_service.create_department"
    },
    {
        "name": "update_department",
        "description": "Update department details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "name": {"type": "string"},
                "is_active": {"type": "boolean"}
            },
            "required": ["code"]
        },
        "handler": "employees.services.org_service.update_department"
    },
    {
        "name": "list_departments",
        "description": "List all departments with employee counts.",
        "input_schema": {"type": "object", "properties": {"active_only": {"type": "boolean"}}},
        "handler": "employees.services.org_service.list_departments"
    },
    {
        "name": "create_team",
        "description": "Create a new project/product team.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "code": {"type": "string"},
                "description": {"type": "string"}
            },
            "required": ["name", "code"]
        },
        "handler": "employees.services.org_service.create_team"
    },
    {
        "name": "update_team",
        "description": "Update team details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "name": {"type": "string"},
                "is_active": {"type": "boolean"}
            },
            "required": ["code"]
        },
        "handler": "employees.services.org_service.update_team"
    },
    {
        "name": "list_teams",
        "description": "List all teams with member counts.",
        "input_schema": {"type": "object", "properties": {"active_only": {"type": "boolean"}}},
        "handler": "employees.services.org_service.list_teams"
    },
    {
        "name": "add_to_team",
        "description": "Add employee to a team.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "team_code": {"type": "string"}
            },
            "required": ["employee_id", "team_code"]
        },
        "handler": "employees.services.org_service.add_to_team"
    },
    {
        "name": "remove_from_team",
        "description": "Remove employee from a team.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "team_code": {"type": "string"}
            },
            "required": ["employee_id", "team_code"]
        },
        "handler": "employees.services.org_service.remove_from_team"
    },
]
