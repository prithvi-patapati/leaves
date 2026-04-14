from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import (
    Bot,
    ConversationLog,
    LLMProvider,
    Pipeline,
    PipelineStep,
    Prompt,
    ToolCallLog,
)


@api_view(['GET'])
def get_prompt(request, role):
    """Return the active prompt template for a given role."""
    role = role.upper()
    valid_roles = [choice[0] for choice in Prompt.ROLE_CHOICES]
    if role not in valid_roles:
        return Response(
            {'error': f'Invalid role. Must be one of: {", ".join(valid_roles)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    prompt = Prompt.objects.filter(role=role, is_active=True).order_by('-version').first()
    if not prompt:
        return Response(
            {'error': f'No active prompt found for role: {role}'},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response({
        'id': prompt.id,
        'name': prompt.name,
        'role': prompt.role,
        'template': prompt.template,
        'version': prompt.version,
    })


@api_view(['GET'])
def get_bot_config(request):
    """Return the active bot config including LLM provider and pipeline steps."""
    bot = Bot.objects.filter(status='active').select_related('llm_provider').first()
    if not bot:
        return Response(
            {'error': 'No active bot found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    pipeline = Pipeline.objects.filter(bot=bot, is_active=True).first()
    steps = []
    if pipeline:
        pipeline_steps = PipelineStep.objects.filter(
            pipeline=pipeline, is_active=True
        ).select_related('llm_provider').order_by('order')
        for step in pipeline_steps:
            step_provider = step.llm_provider or bot.llm_provider
            steps.append({
                'order': step.order,
                'name': step.name,
                'step_type': step.step_type,
                'llm_provider': {
                    'name': step_provider.name,
                    'provider_type': step_provider.provider_type,
                    'model_id': step_provider.model_id,
                    'api_url': step_provider.api_url,
                } if step_provider else None,
                'prompt_override': step.prompt_override or None,
                'config': step.config,
            })

    llm = bot.llm_provider
    return Response({
        'bot': {
            'id': bot.id,
            'name': bot.name,
            'connector_type': bot.connector_type,
            'status': bot.status,
            'config': bot.config,
        },
        'llm_provider': {
            'id': llm.id,
            'name': llm.name,
            'provider_type': llm.provider_type,
            'model_id': llm.model_id,
            'api_url': llm.api_url,
        } if llm else None,
        'pipeline': {
            'id': pipeline.id,
            'name': pipeline.name,
            'steps': steps,
        } if pipeline else None,
    })


@api_view(['POST'])
def log_conversation(request):
    """Log a conversation."""
    data = request.data
    required_fields = ['session_id', 'employee_id', 'role', 'messages']
    missing = [f for f in required_fields if f not in data]
    if missing:
        return Response(
            {'error': f'Missing required fields: {", ".join(missing)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    bot = None
    bot_id = data.get('bot_id')
    if bot_id:
        try:
            bot = Bot.objects.get(id=bot_id)
        except Bot.DoesNotExist:
            return Response(
                {'error': f'Bot with id {bot_id} not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

    conversation = ConversationLog.objects.create(
        bot=bot,
        session_id=data['session_id'],
        employee_id=data['employee_id'],
        role=data['role'],
        messages=data['messages'],
        tool_calls_count=data.get('tool_calls_count', 0),
        llm_calls_count=data.get('llm_calls_count', 0),
    )

    return Response({
        'id': conversation.id,
        'session_id': conversation.session_id,
        'employee_id': conversation.employee_id,
        'started_at': conversation.started_at.isoformat(),
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def log_tool_call(request):
    """Log a tool call."""
    data = request.data
    required_fields = ['tool_name', 'employee_id', 'role']
    missing = [f for f in required_fields if f not in data]
    if missing:
        return Response(
            {'error': f'Missing required fields: {", ".join(missing)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    conversation = None
    conversation_id = data.get('conversation_id')
    if conversation_id:
        try:
            conversation = ConversationLog.objects.get(id=conversation_id)
        except ConversationLog.DoesNotExist:
            return Response(
                {'error': f'Conversation with id {conversation_id} not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

    bot = None
    bot_id = data.get('bot_id')
    if bot_id:
        try:
            bot = Bot.objects.get(id=bot_id)
        except Bot.DoesNotExist:
            return Response(
                {'error': f'Bot with id {bot_id} not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

    tool_call = ToolCallLog.objects.create(
        conversation=conversation,
        bot=bot,
        tool_name=data['tool_name'],
        arguments=data.get('arguments', {}),
        result=data.get('result', {}),
        employee_id=data['employee_id'],
        role=data['role'],
        llm_provider=data.get('llm_provider', ''),
        latency_ms=data.get('latency_ms'),
        success=data.get('success', True),
        error_message=data.get('error_message', ''),
    )

    return Response({
        'id': tool_call.id,
        'tool_name': tool_call.tool_name,
        'success': tool_call.success,
        'created_at': tool_call.created_at.isoformat(),
    }, status=status.HTTP_201_CREATED)
