from django.db import models


class BatchOperation(models.Model):
    ACTION_TYPES = [
        ('CREATE_OVERRIDE', 'Bulk create overrides'),
        ('ADJUST_BALANCE', 'Bulk adjust balances'),
        ('CREDIT_LEAVES', 'Bulk credit leaves'),
    ]
    STATUS_CHOICES = [
        ('PENDING_CONFIRMATION', 'Waiting for HR to confirm'),
        ('EXECUTED', 'Applied successfully'),
        ('ROLLED_BACK', 'Undone by HR'),
        ('FAILED', 'Execution failed'),
    ]

    action_type = models.CharField(max_length=30, choices=ACTION_TYPES)
    filter_criteria = models.JSONField()
    template = models.JSONField()
    affected_count = models.IntegerField(default=0)
    affected_employees = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING_CONFIRMATION')
    created_by = models.ForeignKey(
        'employees.Employee', null=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    rolled_back_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'batch_operations'

    def __str__(self):
        return f"{self.action_type} - {self.status}"
