from django.db import models


class LLMProvider(models.Model):
    """Available AI models that can be used in pipeline steps."""
    PROVIDER_TYPE_CHOICES = [
        ('openai', 'OpenAI'),
        ('local', 'Local'),
        ('anthropic', 'Anthropic'),
    ]

    name = models.CharField(max_length=100)
    provider_type = models.CharField(max_length=20, choices=PROVIDER_TYPE_CHOICES)
    model_id = models.CharField(max_length=100, help_text='e.g. gpt-4o, xlam, gemma')
    api_url = models.URLField(blank=True, default='', help_text='Leave blank for OpenAI. Set for local models.')
    api_key_env = models.CharField(max_length=100, blank=True, default='OPENAI_API_KEY',
                                   help_text='Environment variable name for the API key.')
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bot_llm_provider'
        verbose_name = 'LLM Provider'

    def __str__(self):
        return f"{self.name} ({self.model_id})"


class Prompt(models.Model):
    """Reusable prompt template. Referenced by pipeline steps."""
    name = models.CharField(max_length=200)
    template = models.TextField(
        help_text='Available variables: {name}, {emp_id}, {dept}, {designation}, '
                  '{manager}, {today}, {leave_year}, {role}, '
                  '{user_message}, {tool_results}, {previous_output}')
    is_active = models.BooleanField(default=True)
    version = models.IntegerField(default=1)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bot_prompt'
        verbose_name = 'Prompt'

    def save(self, *args, **kwargs):
        if self.pk:
            self.version += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} (v{self.version})"


class Pipeline(models.Model):
    """An ordered sequence of steps that defines how a bot processes messages.
    Everything lives in the steps — the pipeline is just a container."""
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bot_pipeline'
        verbose_name = 'Pipeline'

    def __str__(self):
        return self.name

    def get_active_steps(self):
        return self.steps.filter(is_active=True).order_by('order')


class PipelineStep(models.Model):
    """A single step in the pipeline. Steps are executed in order.

    Step types:
    - system_prompt: Sets the system prompt for the conversation. No LLM call.
                     Uses the prompt template with employee context variables.
                     Use role_filter to have different prompts per role.
    - tool_call:     Sends message + tools to LLM, executes returned tool calls.
                     Can loop for multiple rounds (config.max_rounds).
    - reply:         Sends message to LLM without tools, returns text response.
                     Use prompt to shape the reply style.
    - classify:      Classifies the message intent. Can route to different paths.
    - validate:      Validates tool call results before proceeding.
    """
    STEP_TYPE_CHOICES = [
        ('system_prompt', 'System Prompt'),
        ('tool_call', 'Tool Call'),
        ('reply', 'Reply'),
        ('classify', 'Classify'),
        ('validate', 'Validate'),
    ]

    ROLE_FILTER_CHOICES = [
        ('', 'All Roles'),
        ('EMPLOYEE', 'Employee Only'),
        ('MANAGER', 'Manager Only'),
        ('ADMIN', 'Admin Only'),
    ]

    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name='steps')
    order = models.IntegerField(help_text='Execution order. Lower runs first.')
    name = models.CharField(max_length=200)
    step_type = models.CharField(max_length=20, choices=STEP_TYPE_CHOICES)
    llm_provider = models.ForeignKey(
        LLMProvider, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pipeline_steps',
        help_text='LLM to use for this step. Not needed for system_prompt steps.')
    prompt = models.ForeignKey(
        Prompt, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pipeline_steps',
        help_text='Prompt template for this step.')
    role_filter = models.CharField(
        max_length=20, choices=ROLE_FILTER_CHOICES, blank=True, default='',
        help_text='Only run this step for this role. Blank = all roles.')
    config = models.JSONField(
        default=dict, blank=True,
        help_text='Step config. tool_call: {"tool_choice": "auto", "max_rounds": 10}. '
                  'reply: {"max_tokens": 500}.')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bot_pipeline_step'
        verbose_name = 'Pipeline Step'
        ordering = ['order']

    def __str__(self):
        role = f" [{self.role_filter}]" if self.role_filter else ""
        return f"Step {self.order}: {self.name}{role}"

    def applies_to_role(self, role):
        return not self.role_filter or self.role_filter == role


class Bot(models.Model):
    """A bot instance. Points to a pipeline that defines its entire behavior."""
    CONNECTOR_TYPE_CHOICES = [
        ('slack', 'Slack'),
        ('whatsapp', 'WhatsApp'),
        ('web', 'Web'),
        ('api', 'API'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('maintenance', 'Maintenance'),
    ]

    name = models.CharField(max_length=200)
    connector_type = models.CharField(max_length=20, choices=CONNECTOR_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    pipeline = models.ForeignKey(
        Pipeline, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bots',
        help_text='Pipeline that defines how this bot processes messages.')
    description = models.TextField(blank=True, default='')
    config = models.JSONField(default=dict, blank=True,
                              help_text='Connector-specific config.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bot_bot'
        verbose_name = 'Bot'

    def __str__(self):
        return f"{self.name} ({self.connector_type})"


class ConversationLog(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.SET_NULL, null=True, blank=True, related_name='conversations')
    session_id = models.CharField(max_length=200)
    employee_id = models.CharField(max_length=50)
    role = models.CharField(max_length=20)
    messages = models.JSONField(default=list)
    tool_calls_count = models.IntegerField(default=0)
    llm_calls_count = models.IntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bot_conversation_log'
        verbose_name = 'Conversation Log'

    def __str__(self):
        return f"{self.employee_id} - {self.session_id}"


class ToolCallLog(models.Model):
    conversation = models.ForeignKey(ConversationLog, on_delete=models.SET_NULL, null=True, blank=True, related_name='tool_calls')
    bot = models.ForeignKey(Bot, on_delete=models.SET_NULL, null=True, blank=True, related_name='tool_calls')
    tool_name = models.CharField(max_length=200)
    arguments = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    employee_id = models.CharField(max_length=50)
    role = models.CharField(max_length=20)
    llm_provider = models.CharField(max_length=100)
    latency_ms = models.IntegerField(null=True, blank=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bot_tool_call_log'
        verbose_name = 'Tool Call Log'

    def __str__(self):
        return f"{self.tool_name} by {self.employee_id}"
