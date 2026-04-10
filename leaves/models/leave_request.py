from django.db import models


class LeaveRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled by employee'),
    ]
    APPLIED_VIA_CHOICES = [
        ('AGENT', 'Via chatbot/agent'),
        ('DASHBOARD', 'Via web dashboard'),
        ('API', 'Via direct API call'),
    ]

    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='leave_requests'
    )
    leave_type = models.ForeignKey('LeaveType', on_delete=models.CASCADE, related_name='requests')

    start_date = models.DateField()
    end_date = models.DateField()
    duration_days = models.DecimalField(max_digits=5, decimal_places=1)
    is_half_day = models.BooleanField(default=False)
    half_day_period = models.CharField(
        max_length=2, null=True, blank=True,
        choices=[('AM', 'First half (morning)'), ('PM', 'Second half (afternoon)')]
    )

    reason = models.TextField()
    document = models.FileField(null=True, blank=True, upload_to='leave_docs/%Y/%m/')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)

    current_approver = models.ForeignKey(
        'employees.Employee', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='pending_approvals'
    )
    approved_by = models.ForeignKey(
        'employees.Employee', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approvals_given'
    )
    approval_remarks = models.TextField(blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    rejected_by = models.ForeignKey(
        'employees.Employee', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='rejections_given'
    )
    rejection_remarks = models.TextField(blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)

    policy_version = models.ForeignKey(
        'LeavePolicyVersion', null=True, blank=True, on_delete=models.SET_NULL
    )

    calendar_event_id = models.CharField(max_length=255, null=True, blank=True)
    calendar_synced = models.BooleanField(default=False)

    applied_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    applied_via = models.CharField(max_length=20, choices=APPLIED_VIA_CHOICES, default='AGENT')
    idempotency_key = models.CharField(max_length=255, unique=True, null=True, blank=True)

    class Meta:
        db_table = 'leave_requests'
        indexes = [
            models.Index(fields=['employee', 'status'], name='idx_request_emp_status'),
            models.Index(fields=['current_approver', 'status'], name='idx_request_approver'),
            models.Index(fields=['start_date', 'end_date'], name='idx_request_dates'),
        ]

    def __str__(self):
        return f"{self.employee} - {self.leave_type.code} ({self.start_date} to {self.end_date})"
