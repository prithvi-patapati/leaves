EMPLOYEE_TOOLS = [
    {
        "name": "apply_leave",
        "description": "Apply for leave. Use leave type CODE (not name): SL=Sick Leave, PL=Planned/Casual Leave, EL=Earned Leave, LOP=Loss of Pay, WFH=Work From Home, BL=Bereavement Leave, ML=Maternity Leave, PtL=Paternity Leave, OH=Optional Holiday. If is_half_day=true, half_day_period (AM or PM) is REQUIRED.",
        "input_schema": {
            "type": "object",
            "properties": {
                "leave_type": {"type": "string", "description": "Leave type code: SL, PL, EL, LOP, WFH, BL, ML, PtL, OH"},
                "start_date": {"type": "string", "format": "date"},
                "end_date": {"type": "string", "format": "date"},
                "reason": {"type": "string"},
                "is_half_day": {"type": "boolean"},
                "half_day_period": {"type": "string", "enum": ["AM", "PM"]},
                "idempotency_key": {"type": "string"}
            },
            "required": ["leave_type", "start_date", "end_date", "reason"]
        },
        "handler": "leaves.services.leave_application.apply_leave"
    },
    {
        "name": "cancel_leave",
        "description": "Cancel a pending or approved leave request. Can cancel PENDING or APPROVED requests. Balance is restored automatically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "integer"},
                "reason": {"type": "string"}
            },
            "required": ["request_id"]
        },
        "handler": "leaves.services.leave_application.cancel_leave"
    },
    {
        "name": "get_my_balance",
        "description": "Get current leave balance for the employee. Returns entitled, used, pending, available days per leave type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"}
            }
        },
        "handler": "leaves.services.balance_manager.get_balances"
    },
    {
        "name": "get_my_requests",
        "description": "Get the employee's leave requests. Returns list with id, leave_type_code, leave_type_name, dates, status, approver.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["PENDING", "APPROVED", "REJECTED", "CANCELLED"]}
            }
        },
        "handler": "leaves.services.leave_application.get_my_requests"
    },
    {
        "name": "get_leave_policy",
        "description": "Get all active leave type configurations. Returns all leave types with entitlement_days, credit_method, advance_notice_days, carry_forward, half_day_allowed, gender_restriction, probation_eligible, and all other policy rules.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": "leaves.services.policy_manager.get_all_policies"
    },
    {
        "name": "validate_leave",
        "description": "Dry-run validation of a leave request. Always call this before apply_leave. Use leave type CODE: SL, PL, EL, LOP, WFH, BL, ML, PtL, OH. If is_half_day=true, half_day_period (AM or PM) is REQUIRED. Returns {valid: true/false, message: error_details}.",
        "input_schema": {
            "type": "object",
            "properties": {
                "leave_type": {"type": "string", "description": "Leave type code: SL, PL, EL, LOP, WFH, BL, ML, PtL, OH"},
                "start_date": {"type": "string", "format": "date"},
                "end_date": {"type": "string", "format": "date"},
                "is_half_day": {"type": "boolean"},
                "half_day_period": {"type": "string", "enum": ["AM", "PM"]}
            },
            "required": ["leave_type", "start_date", "end_date"]
        },
        "handler": "leaves.services.leave_application.validate_leave"
    },
    {
        "name": "get_optional_holidays",
        "description": "List available optional holidays for the year.",
        "input_schema": {
            "type": "object",
            "properties": {"year": {"type": "integer"}}
        },
        "handler": "leaves.services.optional_holiday_service.get_holidays"
    },
    {
        "name": "select_optional_holiday",
        "description": "Select an optional holiday.",
        "input_schema": {
            "type": "object",
            "properties": {"holiday_id": {"type": "integer"}},
            "required": ["holiday_id"]
        },
        "handler": "leaves.services.optional_holiday_service.select_holiday"
    },
]
