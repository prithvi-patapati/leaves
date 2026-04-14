from django.db import models


class LLMProvider(models.Model):
    PROVIDER_TYPE_CHOICES = [
        ('openai', 'OpenAI'),
        ('local', 'Local'),
        ('anthropic', 'Anthropic'),
    ]

    name = models.CharField(max_length=100)
    provider_type = models.CharField(max_length=20, choices=PROVIDER_TYPE_CHOICES)
    model_id = models.CharField(max_length=100)
    api_url = models.URLField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'LLM Provider'
        verbose_name_plural = 'LLM Providers'

    def __str__(self):
        return f"{self.name} ({self.provider_type})"


class Bot(models.Model):
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
    llm_provider = models.ForeignKey(
        LLMProvider,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bots',
    )
    description = models.TextField(blank=True, default='')
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Bot'
        verbose_name_plural = 'Bots'

    def __str__(self):
        return f"{self.name} ({self.connector_type})"


class Prompt(models.Model):
    ROLE_CHOICES = [
        ('EMPLOYEE', 'Employee'),
        ('MANAGER', 'Manager'),
        ('ADMIN', 'Admin'),
        ('SYSTEM', 'System'),
    ]

    name = models.CharField(max_length=200)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    template = models.TextField()
    is_active = models.BooleanField(default=True)
    version = models.IntegerField(default=1)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Prompt'
        verbose_name_plural = 'Prompts'

    def save(self, *args, **kwargs):
        if self.pk:
            self.version += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} (v{self.version})"


class Pipeline(models.Model):
    bot = models.ForeignKey(
        Bot,
        on_delete=models.CASCADE,
        related_name='pipelines',
    )
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pipeline'
        verbose_name_plural = 'Pipelines'

    def __str__(self):
        return f"{self.name} ({self.bot.name})"


class PipelineStep(models.Model):
    STEP_TYPE_CHOICES = [
        ('tool_call', 'Tool Call'),
        ('reply', 'Reply'),
        ('classify', 'Classify'),
        ('validate', 'Validate'),
    ]

    pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.CASCADE,
        related_name='steps',
    )
    order = models.IntegerField()
    name = models.CharField(max_length=200)
    step_type = models.CharField(max_length=20, choices=STEP_TYPE_CHOICES)
    llm_provider = models.ForeignKey(
        LLMProvider,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pipeline_steps',
        help_text='If null, uses the pipeline bot default LLM provider.',
    )
    prompt_override = models.TextField(blank=True, default='')
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pipeline Step'
        verbose_name_plural = 'Pipeline Steps'
        ordering = ['order']

    def __str__(self):
        return f"Step {self.order}: {self.name}"


class ConversationLog(models.Model):
    bot = models.ForeignKey(
        Bot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conversations',
    )
    session_id = models.CharField(max_length=200)
    employee_id = models.CharField(max_length=50)
    role = models.CharField(max_length=20)
    messages = models.JSONField(default=list)
    tool_calls_count = models.IntegerField(default=0)
    llm_calls_count = models.IntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Conversation Log'
        verbose_name_plural = 'Conversation Logs'

    def __str__(self):
        return f"{self.employee_id} - {self.session_id}"


class ToolCallLog(models.Model):
    conversation = models.ForeignKey(
        ConversationLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tool_calls',
    )
    bot = models.ForeignKey(
        Bot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tool_calls',
    )
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
        verbose_name = 'Tool Call Log'
        verbose_name_plural = 'Tool Call Logs'

    def __str__(self):
        return f"{self.tool_name} by {self.employee_id}"
