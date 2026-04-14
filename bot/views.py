import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Bot, Pipeline, Prompt, ConversationLog, ToolCallLog


def get_prompt(request, role):
    """Return the active prompt template for a given role."""
    role = role.upper()
    prompt = Prompt.objects.filter(is_active=True, template__contains='{' + role.lower() + '}').first()
    if not prompt:
        # Fallback: find any active prompt whose name contains the role
        prompt = Prompt.objects.filter(is_active=True, name__icontains=role).order_by('-version').first()
    if not prompt:
        return JsonResponse({'error': f'No active prompt found for role: {role}'}, status=404)

    return JsonResponse({
        'id': prompt.id,
        'name': prompt.name,
        'template': prompt.template,
        'version': prompt.version,
    })


def get_bot_config(request):
    """Return the active bot config including pipeline and steps."""
    bot = Bot.objects.filter(status='active').select_related('pipeline').first()
    if not bot:
        return JsonResponse({'error': 'No active bot found'}, status=404)

    pipeline_data = None
    if bot.pipeline:
        steps = bot.pipeline.get_active_steps().select_related('llm_provider', 'prompt')
        pipeline_data = {
            'id': bot.pipeline.id,
            'name': bot.pipeline.name,
            'steps': [{
                'order': s.order,
                'name': s.name,
                'step_type': s.step_type,
                'role_filter': s.role_filter,
                'llm_provider': {
                    'name': s.llm_provider.name,
                    'provider_type': s.llm_provider.provider_type,
                    'model_id': s.llm_provider.model_id,
                    'api_url': s.llm_provider.api_url,
                } if s.llm_provider else None,
                'prompt': {
                    'name': s.prompt.name,
                    'template': s.prompt.template,
                } if s.prompt else None,
                'config': s.config,
            } for s in steps],
        }

    return JsonResponse({
        'bot': {
            'id': bot.id,
            'name': bot.name,
            'connector_type': bot.connector_type,
            'status': bot.status,
            'config': bot.config,
        },
        'pipeline': pipeline_data,
    })


@csrf_exempt
def log_conversation(request):
    """Log a conversation."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    data = json.loads(request.body)

    bot = None
    if data.get('bot_id'):
        bot = Bot.objects.filter(id=data['bot_id']).first()

    conv = ConversationLog.objects.create(
        bot=bot,
        session_id=data.get('session_id', ''),
        employee_id=data.get('employee_id', ''),
        role=data.get('role', ''),
        messages=data.get('messages', []),
        tool_calls_count=data.get('tool_calls_count', 0),
        llm_calls_count=data.get('llm_calls_count', 0),
    )
    return JsonResponse({'id': conv.id}, status=201)


@csrf_exempt
def log_tool_call(request):
    """Log a tool call."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    data = json.loads(request.body)

    conv = None
    if data.get('conversation_id'):
        conv = ConversationLog.objects.filter(id=data['conversation_id']).first()
    bot = None
    if data.get('bot_id'):
        bot = Bot.objects.filter(id=data['bot_id']).first()

    tc = ToolCallLog.objects.create(
        conversation=conv,
        bot=bot,
        tool_name=data.get('tool_name', ''),
        arguments=data.get('arguments', {}),
        result=data.get('result', {}),
        employee_id=data.get('employee_id', ''),
        role=data.get('role', ''),
        llm_provider=data.get('llm_provider', ''),
        latency_ms=data.get('latency_ms'),
        success=data.get('success', True),
        error_message=data.get('error_message', ''),
    )
    return JsonResponse({'id': tc.id}, status=201)
