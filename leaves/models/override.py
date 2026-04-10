from django.db import models


class EmployeeOverride(models.Model):
    CREATED_VIA_CHOICES = [
        ('AGENT', 'Via chatbot/agent'),
        ('DASHBOARD', 'Via web dashboard'),
        ('ADMIN', 'Via Django admin'),
        ('API', 'Via direct API call'),
    ]

    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='leave_overrides'
    )
    leave_type = models.ForeignKey(
        'LeaveType', on_delete=models.CASCADE, null=True, blank=True, related_name='overrides'
    )

    # Override flags
    block_accrual = models.BooleanField(default=False)
    block_application = models.BooleanField(default=False)
    block_approval = models.BooleanField(default=False)
    modify_entitlement = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    waive_restriction = models.JSONField(default=dict, blank=True)
    custom_approval_chain = models.JSONField(default=list, blank=True)

    # Validity
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    # Audit
    reason = models.TextField()
    created_by = models.ForeignKey(
        'employees.Employee', on_delete=models.SET_NULL, null=True, related_name='overrides_created'
    )
    created_via = models.CharField(max_length=20, choices=CREATED_VIA_CHOICES)
    batch_id = models.ForeignKey(
        'BatchOperation', null=True, blank=True, on_delete=models.SET_NULL
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'employee_overrides'
        indexes = [
            models.Index(
                fields=['employee', 'leave_type', 'effective_from'],
                name='idx_override_lookup',
                condition=models.Q(is_active=True),
            ),
        ]

    def __str__(self):
        return f"Override: {self.employee} - {self.leave_type or 'ALL'}"
