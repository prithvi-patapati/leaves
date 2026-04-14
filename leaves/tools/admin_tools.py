ADMIN_TOOLS = [
    {
        "name": "create_leave_type",
        "description": "Create a new leave type. Required: code (e.g. SL), name, entitlement_days, credit_method (BULK=credited yearly, MONTHLY=accrues monthly, EVENT=credited on specific events like maternity, ON_DEMAND=unlimited like LOP). Optional: approval_chain (e.g. ['REPORTING_MANAGER', 'HR']).",
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
        "description": "Update a leave type's configuration. The 'changes' object can include: entitlement_days, credit_method, half_day_allowed, advance_notice_days, can_apply_in_advance, can_apply_retroactively, document_required, document_required_after_days, gender_restriction, probation_eligible, carry_forward_max, year_end_action (LAPSE/CARRY/CONVERT), approval_chain. Always provide change_summary describing what changed and why.",
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
        "description": "Create a per-employee exception to leave policy. block_application=true prevents them from applying. block_accrual=true stops monthly accrual. modify_entitlement overrides their annual entitlement days. waive_restriction is a dict of policy fields to override (e.g. {'probation_eligible': true} to allow WFH during probation). leave_type_code is optional — null means applies to ALL leave types. effective_from and effective_to define the date range.",
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
        "description": "Manually credit or deduct leave days. Positive days = credit (reward/correction). Negative days = deduct (penalty/correction). Creates an audit trail in the ledger.",
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
        "description": "Create overrides for multiple employees at once. filter_criteria can include: {department: 'ENGINEERING', probation_status: 'ON_PROBATION', employment_type: 'INTERN'}. override_template has the same fields as create_override (block_application, block_accrual, etc). Returns a PREVIEW — must call confirm_batch to execute.",
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
        "description": "Execute a pending batch operation. Only works on PENDING_CONFIRMATION batches. This actually creates the overrides for all matched employees.",
        "input_schema": {
            "type": "object",
            "properties": {"batch_id": {"type": "integer"}},
            "required": ["batch_id"]
        },
        "handler": "leaves.services.batch_manager.confirm_batch"
    },
    {
        "name": "rollback_batch",
        "description": "Undo an executed batch. Deactivates all overrides created by the batch. Only works on EXECUTED batches.",
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
        "description": "Set a backup approver for when a manager is on leave. employee_id is the employee whose requests need an approver. primary_manager_id is their normal manager. fallback_manager_id is the backup. effective_from/to define the date range.",
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
        "description": "Credit annual leave balances for all employees. Only credits BULK-type leaves (e.g. SL, WFH). Run once per year in April. Optional leave_type to credit only one type.",
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
        "description": "Run monthly leave accrual for MONTHLY-type leaves (e.g. PL, EL). Credits monthly_accrual_rate days to each employee. Run once per month.",
        "input_schema": {
            "type": "object",
            "properties": {"date": {"type": "string", "format": "date"}}
        },
        "handler": "leaves.services.accrual.run_monthly_accrual"
    },
    {
        "name": "trigger_year_end",
        "description": "Run year-end processing. LAPSE types: unused balance expires. CARRY types: carry forward up to carry_forward_max, rest lapses. CONVERT types: unused balance converts to another leave type. ALWAYS run with dry_run=true first to preview, then dry_run=false to execute.",
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
        "description": "View all leave requests across the company. Filter by status (PENDING/APPROVED/REJECTED/CANCELLED) and/or employee_id.",
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
