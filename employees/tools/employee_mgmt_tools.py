EMPLOYEE_MGMT_TOOLS = [
    {
        "name": "add_employee",
        "description": "Add new joiner. Triggers onboarding templates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "email": {"type": "string"},
                "gender": {"type": "string", "enum": ["M", "F", "O"]},
                "department_code": {"type": "string"},
                "designation_title": {"type": "string"},
                "date_of_joining": {"type": "string", "format": "date"},
                "employment_type": {"type": "string", "enum": ["FULL_TIME", "INTERN", "CONTRACT", "CONSULTANT"]},
                "reporting_manager_id": {"type": "string"},
                "phone": {"type": "string"},
            },
            "required": ["employee_id", "first_name", "email", "gender", "department_code", "designation_title", "date_of_joining"]
        },
        "handler": "employees.services.employee_service.add_employee"
    },
    {
        "name": "update_employee",
        "description": "Update employee fields.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "changes": {"type": "object"}
            },
            "required": ["employee_id", "changes"]
        },
        "handler": "employees.services.employee_service.update_employee"
    },
    {
        "name": "confirm_employee",
        "description": "End probation for employee.",
        "input_schema": {
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"]
        },
        "handler": "employees.services.employee_service.confirm_employee"
    },
    {
        "name": "deactivate_employee",
        "description": "Deactivate employee (exit).",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "last_working_date": {"type": "string", "format": "date"},
                "exit_reason": {"type": "string", "enum": ["RESIGNED", "TERMINATED", "CONTRACT_END", "INTERNSHIP_END"]}
            },
            "required": ["employee_id", "last_working_date", "exit_reason"]
        },
        "handler": "employees.services.employee_service.deactivate_employee"
    },
    {
        "name": "transfer_employee",
        "description": "Transfer employee — change dept/manager/designation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "department_code": {"type": "string"},
                "reporting_manager_id": {"type": "string"},
                "designation_title": {"type": "string"}
            },
            "required": ["employee_id"]
        },
        "handler": "employees.services.employee_service.transfer_employee"
    },
    {
        "name": "get_employee",
        "description": "Get full employee details.",
        "input_schema": {
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"]
        },
        "handler": "employees.services.employee_service.get_employee"
    },
    {
        "name": "search_employees",
        "description": "Search employees by various filters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "department": {"type": "string"},
                "team": {"type": "string"},
                "designation": {"type": "string"},
                "probation_status": {"type": "string"},
                "reporting_manager": {"type": "string"},
                "name": {"type": "string"},
                "is_active": {"type": "boolean"}
            }
        },
        "handler": "employees.services.employee_service.search_employees"
    },
]
