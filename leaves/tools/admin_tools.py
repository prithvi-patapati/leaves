ADMIN_TOOLS = [
    {
        "name": "create_leave_type",
        "description": "Create a new leave type/policy.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "name": {"type": "string"},
                "entitlement_days": {"type": "number"},
                "credit_method": {"type": "string", "enum": ["BULK", "MONTHLY", "EVENT", "ON_DEMAND"]},
                "approval_chain": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["code", "name", "entitlement_days", "credit_method"]
        },
        "handler": "leaves.services.policy_manager.create_leave_type"
    },
    {
        "name": "update_leave_type",
        "description": "Update leave type configuration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "changes": {"type": "object"},
                "change_summary": {"type": "string"},
                "effective_mode": {"type": "string", "enum": ["PROSPECTIVE", "RETROACTIVE"]}
            },
            "required": ["code", "changes", "change_summary"]
        },
        "handler": "leaves.services.policy_manager.update_leave_type"
    },
    {
        "name": "deactivate_leave_type",
        "description": "Deactivate a leave type.",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"]
        },
        "handler": "leaves.services.policy_manager.deactivate_leave_type"
    },
    {
        "name": "create_override",
        "description": "Create per-employee leave override.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "leave_type_code": {"type": "string"},
                "block_accrual": {"type": "boolean"},
                "block_application": {"type": "boolean"},
                "modify_entitlement": {"type": "number"},
                "waive_restriction": {"type": "object"},
                "effective_from": {"type": "string", "format": "date"},
                "effective_to": {"type": "string", "format": "date"},
                "reason": {"type": "string"}
            },
            "required": ["employee_id", "effective_from", "reason"]
        },
        "handler": "leaves.services.override_manager.create_override"
    },
    {
        "name": "remove_override",
        "description": "Deactivate an override.",
        "input_schema": {
            "type": "object",
            "properties": {
                "override_id": {"type": "integer"},
                "reason": {"type": "string"}
            },
            "required": ["override_id"]
        },
        "handler": "leaves.services.override_manager.remove_override"
    },
    {
        "name": "get_overrides",
        "description": "List overrides for an employee or leave type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "leave_type": {"type": "string"}
            }
        },
        "handler": "leaves.services.override_manager.get_overrides"
    },
    {
        "name": "adjust_balance",
        "description": "Manual balance adjustment by HR.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "leave_type": {"type": "string"},
                "days": {"type": "number"},
                "reason": {"type": "string"}
            },
            "required": ["employee_id", "leave_type", "days", "reason"]
        },
        "handler": "leaves.services.balance_manager.adjust_balance"
    },
    {
        "name": "bulk_create_overrides",
        "description": "Create overrides for multiple employees.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter_criteria": {"type": "object"},
                "override_template": {"type": "object"}
            },
            "required": ["filter_criteria", "override_template"]
        },
        "handler": "leaves.services.batch_manager.bulk_create_overrides"
    },
    {
        "name": "confirm_batch",
        "description": "Confirm and execute a pending batch operation.",
        "input_schema": {
            "type": "object",
            "properties": {"batch_id": {"type": "integer"}},
            "required": ["batch_id"]
        },
        "handler": "leaves.services.batch_manager.confirm_batch"
    },
    {
        "name": "rollback_batch",
        "description": "Rollback an executed batch operation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "integer"},
                "reason": {"type": "string"}
            },
            "required": ["batch_id", "reason"]
        },
        "handler": "leaves.services.batch_manager.rollback_batch"
    },
    {
        "name": "set_fallback_manager",
        "description": "Set a fallback approver when manager is on leave.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "primary_manager_id": {"type": "string"},
                "fallback_manager_id": {"type": "string"},
                "effective_from": {"type": "string", "format": "date"},
                "effective_to": {"type": "string", "format": "date"},
                "reason": {"type": "string"}
            },
            "required": ["employee_id", "primary_manager_id", "fallback_manager_id"]
        },
        "handler": "leaves.services.fallback_service.set_fallback"
    },
    {
        "name": "trigger_bulk_credit",
        "description": "Run bulk credit for a leave year.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "leave_type": {"type": "string"}
            },
            "required": ["year"]
        },
        "handler": "leaves.services.accrual.run_bulk_credit"
    },
    {
        "name": "trigger_monthly_accrual",
        "description": "Run monthly accrual for current month.",
        "input_schema": {
            "type": "object",
            "properties": {"date": {"type": "string", "format": "date"}}
        },
        "handler": "leaves.services.accrual.run_monthly_accrual"
    },
    {
        "name": "trigger_year_end",
        "description": "Run year-end processing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "dry_run": {"type": "boolean"}
            },
            "required": ["year"]
        },
        "handler": "leaves.services.year_end.run_year_end_processing"
    },
    {
        "name": "get_all_requests",
        "description": "Get all leave requests (admin view).",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "employee_id": {"type": "string"}
            }
        },
        "handler": "leaves.services.leave_application.get_all_requests"
    },
    {
        "name": "create_optional_holiday",
        "description": "Create an optional holiday for employees to select.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "date": {"type": "string", "format": "date"},
                "year": {"type": "integer"},
                "description": {"type": "string"}
            },
            "required": ["name", "date"]
        },
        "handler": "leaves.services.optional_holiday_service.create_holiday"
    },
]
