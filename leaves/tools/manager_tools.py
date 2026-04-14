MANAGER_TOOLS = [
    {
        "name": "get_team_requests",
        "description": "Get leave requests from your direct reports. Each result has an 'id' field — use that as 'request_id' when approving or rejecting.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["PENDING", "APPROVED", "REJECTED", "CANCELLED"]}
            }
        },
        "handler": "leaves.services.leave_application.get_team_requests"
    },
    {
        "name": "approve_leave",
        "description": "Approve a pending leave request. The request_id is the 'id' field from get_team_requests results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "integer", "description": "The 'id' from get_team_requests (e.g. 1, 2, 3)"},
                "remarks": {"type": "string"}
            },
            "required": ["request_id"]
        },
        "handler": "leaves.services.leave_approval.approve_leave"
    },
    {
        "name": "reject_leave",
        "description": "Reject a pending leave request. The request_id is the 'id' field from get_team_requests results. remarks are mandatory — the employee will see the rejection reason.",
        "input_schema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "integer", "description": "The 'id' from get_team_requests (e.g. 1, 2, 3)"},
                "remarks": {"type": "string"}
            },
            "required": ["request_id", "remarks"]
        },
        "handler": "leaves.services.leave_approval.reject_leave"
    },
    {
        "name": "get_team_balance",
        "description": "Get leave balances of your direct reports. Returns leave balances for all your direct reports with employee_code, employee_name, leave_type_code, entitled, used, available.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": "leaves.services.balance_manager.get_team_balances"
    },
    {
        "name": "get_team_calendar",
        "description": "View team leave calendar for a date range. Returns approved leave requests within the date range for your direct reports. Use to check who is off on specific days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "format": "date"},
                "end_date": {"type": "string", "format": "date"}
            },
            "required": ["start_date", "end_date"]
        },
        "handler": "leaves.services.calendar_service.get_team_calendar"
    },
    {
        "name": "approve_optional_holiday",
        "description": "Approve an optional holiday selection.",
        "input_schema": {
            "type": "object",
            "properties": {"selection_id": {"type": "integer"}},
            "required": ["selection_id"]
        },
        "handler": "leaves.services.optional_holiday_service.approve_selection"
    },
]
