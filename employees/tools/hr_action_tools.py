HR_ACTION_TOOLS = [
    {
        "name": "get_pending_hr_actions",
        "description": "View open HR nudges/actions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["OPEN", "RESOLVED", "DISMISSED"]},
                "priority": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]}
            }
        },
        "handler": "leaves.services.hr_action_service.get_pending"
    },
    {
        "name": "resolve_hr_action",
        "description": "Mark an HR action as resolved or dismissed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action_id": {"type": "integer"},
                "status": {"type": "string", "enum": ["RESOLVED", "DISMISSED"]},
                "notes": {"type": "string"}
            },
            "required": ["action_id"]
        },
        "handler": "leaves.services.hr_action_service.resolve_action"
    },
    {
        "name": "execute_suggested_action",
        "description": "Execute a suggested fix from an HR action.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action_id": {"type": "integer"},
                "suggestion_index": {"type": "integer"}
            },
            "required": ["action_id", "suggestion_index"]
        },
        "handler": "leaves.services.hr_action_service.execute_suggested_action"
    },
]
