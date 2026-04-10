from django.db import models


class LeaveType(models.Model):
    CREDIT_METHODS = [
        ('BULK', 'Bulk credit at year start'),
        ('MONTHLY', 'Monthly accrual'),
        ('EVENT', 'Event-based (maternity, paternity, bereavement)'),
        ('ON_DEMAND', 'On demand / unlimited (LOP)'),
    ]
    YEAR_END_ACTIONS = [
        ('LAPSE', 'Unused days lapse — balance resets to 0'),
        ('CARRY', 'Carry forward up to max cap'),
        ('CONVERT', 'Convert unused to another leave type'),
    ]

    # Identity
    code = models.CharField(max_length=10, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    # Entitlement & Credit
    entitlement_days = models.DecimalField(max_digits=6, decimal_places=1)
    credit_method = models.CharField(max_length=20, choices=CREDIT_METHODS)
    monthly_accrual_rate = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    is_pro_rata = models.BooleanField(default=True)

    # Year-End
    year_end_action = models.CharField(max_length=20, choices=YEAR_END_ACTIONS, default='LAPSE')
    carry_forward_max = models.IntegerField(default=0)
    convert_to = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='converted_from'
    )

    # Restrictions & Eligibility
    half_day_allowed = models.BooleanField(default=True)
    advance_notice_days = models.IntegerField(default=0)
    can_apply_in_advance = models.BooleanField(default=True)
    can_apply_retroactively = models.BooleanField(default=False)
    document_required = models.BooleanField(default=False)
    document_required_after_days = models.IntegerField(default=0)
    gender_restriction = models.CharField(
        max_length=1, null=True, blank=True,
        choices=[('M', 'Male only'), ('F', 'Female only')]
    )
    min_service_days = models.IntegerField(default=0)
    avail_window_days = models.IntegerField(null=True, blank=True)
    probation_eligible = models.BooleanField(default=True)
    consecutive_day_restriction = models.BooleanField(default=False)
    max_continuous_days_before_flag = models.IntegerField(null=True, blank=True)

    # Approval
    requires_approval = models.BooleanField(default=True)
    approval_chain = models.JSONField(default=list)

    # Metadata
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'leave_types'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class LeavePolicyVersion(models.Model):
    EFFECTIVE_MODES = [
        ('PROSPECTIVE', 'Applies from next cycle only'),
        ('RETROACTIVE', 'Top-up/adjust current year balances'),
    ]
    CHANGED_VIA_CHOICES = [
        ('AGENT', 'Via chatbot/agent'),
        ('DASHBOARD', 'Via web dashboard'),
        ('ADMIN', 'Via Django admin'),
        ('API', 'Via direct API call'),
    ]

    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name='versions')
    version = models.IntegerField()
    snapshot = models.JSONField()
    change_summary = models.TextField()
    effective_mode = models.CharField(max_length=20, choices=EFFECTIVE_MODES, default='PROSPECTIVE')
    changed_by = models.ForeignKey(
        'employees.Employee', on_delete=models.SET_NULL, null=True, related_name='policy_changes_made'
    )
    changed_via = models.CharField(max_length=20, choices=CHANGED_VIA_CHOICES)
    session_id = models.CharField(max_length=255, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    notification_sent = models.BooleanField(default=False)
    notification_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'leave_policy_versions'
        unique_together = ('leave_type', 'version')
        ordering = ['-version']

    def __str__(self):
        return f"{self.leave_type.code} v{self.version}"
