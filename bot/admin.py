from django.contrib import admin
from .models import (
    LLMProvider,
    Bot,
    Prompt,
    Pipeline,
    PipelineStep,
    ConversationLog,
    ToolCallLog,
)


@admin.register(LLMProvider)
class LLMProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider_type', 'model_id', 'is_active')
    list_filter = ('provider_type', 'is_active')
    search_fields = ('name', 'model_id')


@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    list_display = ('name', 'connector_type', 'status', 'llm_provider')
    list_filter = ('connector_type', 'status')
    search_fields = ('name',)


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'is_active', 'version')
    list_filter = ('role', 'is_active')
    search_fields = ('name', 'template')
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'role', 'is_active', 'version', 'description'),
        }),
        ('Prompt Template', {
            'fields': ('template',),
            'description': (
                'Available variables: {name}, {emp_id}, {dept}, {designation}, '
                '{manager}, {today}, {leave_year}'
            ),
        }),
    )
    formfield_overrides = {}

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['template'].widget.attrs.update({
            'rows': 25,
            'cols': 120,
            'style': 'font-family: monospace; width: 100%;',
        })
        return form


class PipelineStepInline(admin.TabularInline):
    model = PipelineStep
    extra = 1
    ordering = ('order',)
    fields = ('order', 'name', 'step_type', 'llm_provider', 'is_active', 'config')


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ('name', 'bot', 'is_active')
    list_filter = ('is_active', 'bot')
    search_fields = ('name',)
    inlines = [PipelineStepInline]


@admin.register(PipelineStep)
class PipelineStepAdmin(admin.ModelAdmin):
    list_display = ('name', 'pipeline', 'order', 'step_type', 'llm_provider', 'is_active')
    list_filter = ('step_type', 'is_active')
    search_fields = ('name',)


@admin.register(ConversationLog)
class ConversationLogAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'employee_id', 'role', 'tool_calls_count', 'started_at')
    list_filter = ('role', 'bot')
    search_fields = ('session_id', 'employee_id')
    readonly_fields = ('messages', 'started_at', 'last_message_at')


@admin.register(ToolCallLog)
class ToolCallLogAdmin(admin.ModelAdmin):
    list_display = ('tool_name', 'employee_id', 'success', 'latency_ms', 'created_at')
    list_filter = ('tool_name', 'success', 'role')
    search_fields = ('tool_name', 'employee_id')
    readonly_fields = ('created_at',)
