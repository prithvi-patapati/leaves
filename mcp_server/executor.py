import importlib
from datetime import date
from decimal import Decimal
from employees.models import Employee
from .registry import get_tool_by_name


class ToolExecutionError(Exception):
    pass


_ERROR_TRANSLATIONS = {
    'LeaveType matching query does not exist': 'That leave type does not exist. Check the code (SL, PL, EL, etc).',
    'Employee.DoesNotExist': 'Employee not found. Check the employee ID.',
    'Insufficient balance': 'Not enough leave days available.',
    'cannot be applied in advance': 'This leave type cannot be applied in advance. Apply on or after the day.',
    'cannot be applied retroactively': 'This leave type cannot be applied retroactively.',
    'not the current approver': 'You are not the approver for this request.',
    'not pending': 'This request is not pending anymore.',
    'maximum recursion': 'Internal error. Please try again.',
}


def _translate_error(error_str):
    for key, friendly in _ERROR_TRANSLATIONS.items():
        if key in error_str:
            return friendly
    return error_str


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
    'validate_leave': {'leave_type': 'leave_type_code'},
    'adjust_balance': {'leave_type': 'leave_type_code'},
    'get_overrides': {'leave_type': 'leave_type_code'},
    'trigger_bulk_credit': {'leave_type': 'leave_type_code'},
    'trigger_monthly_accrual': {'date': 'execution_date'},
    'trigger_year_end': {'year': 'ending_year'},
    'create_optional_holiday': {'date': 'date_val'},
    'transfer_employee': {
        'department_code': 'department',
        'reporting_manager_id': 'reporting_manager',
        'designation_title': 'designation',
    },
}

# Tools where all args should be packed into a single dict param
_PACK_AS_DICT = {
    'create_leave_type': 'config_dict',
}

# Tools where a 'changes' dict arg should be unpacked into **kwargs
_UNPACK_CHANGES = {'update_employee'}


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

    # Resolve FK references for employee tools that need model instances
    if tool_name in ('add_employee', 'transfer_employee'):
        from employees.models import Department, Designation
        # department code → Department instance
        dept_key = 'department_code' if 'department_code' in processed_args else 'department' if isinstance(processed_args.get('department'), str) else None
        if dept_key:
            code = processed_args.pop(dept_key)
            try:
                processed_args['department'] = Department.objects.get(code=code)
            except Department.DoesNotExist:
                return {"error": f"Department not found: {code}"}
        # designation title → Designation instance
        desg_key = 'designation_title' if 'designation_title' in processed_args else 'designation' if isinstance(processed_args.get('designation'), str) else None
        if desg_key:
            title = processed_args.pop(desg_key)
            try:
                processed_args['designation'] = Designation.objects.get(title=title)
            except Designation.DoesNotExist:
                return {"error": f"Designation not found: {title}"}
        # reporting manager id → Employee instance
        mgr_key = 'reporting_manager_id' if 'reporting_manager_id' in processed_args else 'reporting_manager' if isinstance(processed_args.get('reporting_manager'), str) else None
        if mgr_key:
            mgr_id = processed_args.pop(mgr_key)
            try:
                processed_args['reporting_manager'] = Employee.objects.get(employee_id=mgr_id)
            except Employee.DoesNotExist:
                return {"error": f"Manager not found: {mgr_id}"}

    # Pack all args into a single dict param (e.g., create_leave_type expects config_dict)
    if tool_name in _PACK_AS_DICT:
        dict_param = _PACK_AS_DICT[tool_name]
        processed_args = {dict_param: processed_args}

    # Unpack 'changes' dict into kwargs (e.g., update_employee uses **changes)
    if tool_name in _UNPACK_CHANGES and 'changes' in processed_args:
        changes = processed_args.pop('changes')
        processed_args.update(changes)

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
        return {"error": _translate_error(str(e))}


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


# Internal FK fields to drop when enriched readable versions are present
_DROP_FK_FIELDS = {
    'leave_type_id', 'current_approver_id', 'approved_by_id',
    'rejected_by_id', 'policy_version_id', 'calendar_event_id',
    'calendar_synced', 'applied_via', 'idempotency_key',
    'department_id', 'designation_id', 'reporting_manager_id',
    'created_by_id',
}


def _serialize_result(result):
    if result is None:
        return {"result": None}
    if isinstance(result, dict):
        return result
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], bool):
        return {"valid": result[0], "message": str(result[1]) if result[1] else None}
    if isinstance(result, (list, tuple)):
        return {"results": [_serialize_result(item) for item in result]}
    if hasattr(result, '__dict__') and hasattr(result, 'pk'):
        data = {}
        for field in result._meta.get_fields():
            if hasattr(field, 'attname'):
                name = field.attname
                if name in _DROP_FK_FIELDS:
                    continue
                val = getattr(result, name, None)
                if isinstance(val, date):
                    val = val.isoformat()
                elif isinstance(val, Decimal):
                    val = str(val)
                data[name] = val
        # Enrich with readable names for common FK relations
        if hasattr(result, 'leave_type_id') and hasattr(result, 'leave_type'):
            lt = result.leave_type
            if lt:
                data['leave_type_code'] = lt.code
                data['leave_type_name'] = lt.name
        if hasattr(result, 'employee_id') and hasattr(result, 'employee'):
            emp = result.employee
            if emp and hasattr(emp, 'employee_id'):
                data['employee_code'] = emp.employee_id
                data['employee_name'] = emp.full_name
                # Replace raw FK integer with readable employee code
                if 'employee_id' in data and isinstance(data['employee_id'], int):
                    data.pop('employee_id')
        if hasattr(result, 'current_approver_id') and hasattr(result, 'current_approver'):
            approver = result.current_approver
            if approver:
                data['approver'] = approver.full_name
        if hasattr(result, 'department_id') and hasattr(result, 'department'):
            dept = result.department
            if dept:
                data['department_name'] = dept.name
                data['department_code'] = dept.code
        if hasattr(result, 'designation_id') and hasattr(result, 'designation'):
            desg = result.designation
            if desg:
                data['designation_name'] = desg.title
        if hasattr(result, 'reporting_manager_id') and hasattr(result, 'reporting_manager'):
            mgr = result.reporting_manager
            if mgr:
                data['manager_name'] = mgr.full_name
                data['manager_id'] = mgr.employee_id
        if hasattr(result, 'available'):
            data['available'] = str(result.available)
        return data
    if hasattr(result, '__iter__') and not isinstance(result, (str, bytes)):
        return {"results": [_serialize_result(item) for item in result]}
    return {"result": str(result)}
