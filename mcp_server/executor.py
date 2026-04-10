import importlib
from datetime import date
from decimal import Decimal
from employees.models import Employee
from .registry import get_tool_by_name


class ToolExecutionError(Exception):
    pass


# Tools that need `employee` (the caller) as first positional arg
_EMPLOYEE_PARAM_TOOLS = {
    'apply_leave', 'cancel_leave', 'validate_leave',
}

# Tools that need `approver` (the caller) as first positional arg
_APPROVER_PARAM_TOOLS = {
    'approve_leave', 'reject_leave',
}

# Tools where the caller's employee_id should be injected
_INJECT_EMPLOYEE_ID = {
    'get_my_balance': 'employee_id',
    'get_my_requests': 'employee_id',
}

# Argument name remapping per tool
_ARG_REMAP = {
    'apply_leave': {'leave_type': 'leave_type_code'},
}


def execute_tool(tool_name, arguments, user_context):
    tool = get_tool_by_name(tool_name)
    if not tool:
        return {"error": f"Unknown tool: {tool_name}"}

    handler_path = tool['handler']
    module_path, func_name = handler_path.rsplit('.', 1)

    try:
        module = importlib.import_module(module_path)
        handler = getattr(module, func_name)
    except (ImportError, AttributeError) as e:
        return {"error": f"Tool handler not found: {handler_path} ({e})"}

    try:
        employee = Employee.objects.get(employee_id=user_context.get('employee_id'))
    except Employee.DoesNotExist:
        return {"error": f"Employee not found: {user_context.get('employee_id')}"}

    processed_args = _process_arguments(arguments)

    # Remap argument names
    if tool_name in _ARG_REMAP:
        for old_key, new_key in _ARG_REMAP[tool_name].items():
            if old_key in processed_args:
                processed_args[new_key] = processed_args.pop(old_key)

    # Inject caller's employee_id for self-referencing tools
    if tool_name in _INJECT_EMPLOYEE_ID:
        param_name = _INJECT_EMPLOYEE_ID[tool_name]
        if param_name not in processed_args:
            processed_args[param_name] = employee.employee_id

    try:
        if tool_name in _EMPLOYEE_PARAM_TOOLS:
            result = handler(employee=employee, **processed_args)
        elif tool_name in _APPROVER_PARAM_TOOLS:
            result = handler(approver=employee, **processed_args)
        elif 'actor' in _get_params(handler):
            result = handler(actor=employee, **processed_args)
        else:
            result = handler(**processed_args)

        return _serialize_result(result)
    except Exception as e:
        return {"error": str(e)}


def _get_params(func):
    """Get parameter names for a function, handling wrapped functions."""
    import inspect
    try:
        sig = inspect.signature(func)
        return tuple(sig.parameters.keys())
    except (ValueError, TypeError):
        return ()


def _process_arguments(args):
    processed = {}
    for key, value in args.items():
        if isinstance(value, str) and _looks_like_date(value):
            try:
                processed[key] = date.fromisoformat(value)
            except ValueError:
                processed[key] = value
        else:
            processed[key] = value
    return processed


def _looks_like_date(s):
    return len(s) == 10 and s.count('-') == 2


def _serialize_result(result):
    if result is None:
        return {"result": None}
    if isinstance(result, dict):
        return result
    if isinstance(result, (list, tuple)):
        return {"results": [_serialize_result(item) for item in result]}
    if hasattr(result, '__dict__') and hasattr(result, 'pk'):
        data = {}
        for field in result._meta.get_fields():
            if hasattr(field, 'attname'):
                val = getattr(result, field.attname, None)
                if isinstance(val, date):
                    val = val.isoformat()
                elif isinstance(val, Decimal):
                    val = str(val)
                data[field.attname] = val
        return data
    if hasattr(result, '__iter__'):
        return {"results": [_serialize_result(item) for item in result]}
    return {"result": str(result)}
