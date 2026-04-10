"""
HTTP endpoint for tool execution. The Slack connector calls this
to execute HRMS tools over HTTP instead of direct Python imports.
"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json


@csrf_exempt
def tool_list(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    role = body.get('role', 'EMPLOYEE')

    from mcp_server.registry import get_tools_for_role
    tools = get_tools_for_role(role)

    clean_tools = []
    for t in tools:
        clean_tools.append({
            'name': t['name'],
            'description': t['description'],
            'input_schema': t['input_schema'],
        })

    return JsonResponse({'tools': clean_tools})


@csrf_exempt
def tool_execute(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    tool_name = body.get('tool')
    args = body.get('args', {})
    employee_id = body.get('employee_id')
    role = body.get('role', 'EMPLOYEE')

    if not tool_name:
        return JsonResponse({'error': 'Missing tool name'}, status=400)
    if not employee_id:
        return JsonResponse({'error': 'Missing employee_id'}, status=400)

    from mcp_server.executor import execute_tool
    try:
        result = execute_tool(tool_name, args, {
            'employee_id': employee_id,
            'role': role,
        })
        return JsonResponse({'result': result}, json_dumps_params={'default': str})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
