from django.contrib import admin
from .models import LLMProvider, Prompt, Pipeline, PipelineStep, Bot, ConversationLog, ToolCallLog


@admin.register(LLMProvider)
class LLMProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider_type', 'model_id', 'is_active')
    list_filter = ('provider_type', 'is_active')


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'version', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'template')

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['template'].widget.attrs.update({
            'rows': 25, 'cols': 120, 'style': 'font-family: monospace; width: 100%;',
        })
        return form


class PipelineStepInline(admin.TabularInline):
    model = PipelineStep
    extra = 0
    ordering = ('order',)
    fields = ('order', 'name', 'step_type', 'llm_provider', 'prompt', 'role_filter', 'is_active')


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'step_count', 'updated_at')
    inlines = [PipelineStepInline]

    def step_count(self, obj):
        return obj.steps.filter(is_active=True).count()
    step_count.short_description = 'Active Steps'


@admin.register(PipelineStep)
class PipelineStepAdmin(admin.ModelAdmin):
    list_display = ('pipeline', 'order', 'name', 'step_type', 'llm_provider', 'prompt', 'role_filter', 'is_active')
    list_filter = ('step_type', 'pipeline', 'role_filter', 'is_active')
    ordering = ('pipeline', 'order')


@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    list_display = ('name', 'connector_type', 'status', 'pipeline')
    list_filter = ('connector_type', 'status')


@admin.register(ConversationLog)
class ConversationLogAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'employee_id', 'role', 'tool_calls_count', 'llm_calls_count', 'started_at')
    list_filter = ('role', 'bot')
    readonly_fields = ('messages', 'started_at', 'last_message_at')
    search_fields = ('employee_id', 'session_id')


@admin.register(ToolCallLog)
class ToolCallLogAdmin(admin.ModelAdmin):
    list_display = ('tool_name', 'employee_id', 'role', 'success', 'latency_ms', 'created_at')
    list_filter = ('tool_name', 'success', 'role')
    readonly_fields = ('arguments', 'result', 'created_at')
    search_fields = ('tool_name', 'employee_id')
