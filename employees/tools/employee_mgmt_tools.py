EMPLOYEE_MGMT_TOOLS = [
    {
        "name": "add_employee",
        "description": "Add a new employee. Triggers onboarding templates automatically. department_code must match an existing department (e.g. ENGINEERING, HR, ADMIN). designation_title must match an existing designation (e.g. Software Engineer, Senior Project Manager, CEO).",
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
        "description": "Update employee fields. The changes object can include: first_name, last_name, email, phone, gender, employment_type, probation_status. Example: {'phone': '9876543210'}.",
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
        "description": "End probation and confirm the employee. Changes probation_status to CONFIRMED. Unlocks leave types restricted during probation (e.g. WFH, PtL).",
        "input_schema": {
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"]
        },
        "handler": "employees.services.employee_service.confirm_employee"
    },
    {
        "name": "deactivate_employee",
        "description": "Process employee exit. Sets is_active=false, records last_working_date and exit_reason. Cancels all pending leave requests. Creates an EXIT HR action for follow-up.",
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
        "description": "Transfer employee to a different department, reporting manager, or designation. At least one of department_code, reporting_manager_id, or designation_title is required.",
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
        "description": "Get complete employee details including department, designation, reporting manager, teams, employment type, probation status, and dates.",
        "input_schema": {
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"]
        },
        "handler": "employees.services.employee_service.get_employee"
    },
    {
        "name": "search_employees",
        "description": "Search employees by filters. All filters are optional and combinable. department accepts department name (e.g. 'Engineering'). name does partial match. Returns list with employee_id, full_name, department, designation, manager.",
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
