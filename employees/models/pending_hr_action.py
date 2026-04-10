from django.db import models


class PendingHRAction(models.Model):
    TRIGGER_TYPES = [
        ('DEPARTMENT_CHANGE', 'Employee moved to a different department'),
        ('MANAGER_CHANGE', 'Reporting manager changed'),
        ('CONFIRMATION', 'Employee confirmed (probation ended)'),
        ('NOTICE_PERIOD', 'Employee on notice period'),
        ('EXIT', 'Employee deactivated'),
        ('TEAM_CHANGE', 'Employee added/removed from a team'),
        ('DESIGNATION_CHANGE', 'Designation changed'),
        ('NEW_JOINER', 'New employee added — verify onboarding'),
        ('MANAGER_ON_LEAVE', 'Manager with pending approvals went on leave'),
    ]
    STATUS_CHOICES = [
        ('OPEN', 'Needs HR attention'),
        ('RESOLVED', 'HR took action'),
        ('DISMISSED', 'HR reviewed, no action needed'),
        ('AUTO_RESOLVED', 'Resolved by a subsequent action'),
    ]
    PRIORITY_CHOICES = [
        ('HIGH', 'Urgent — affects active requests'),
        ('MEDIUM', 'Should review soon'),
        ('LOW', 'Informational'),
    ]

    trigger_type = models.CharField(max_length=30, choices=TRIGGER_TYPES)
    employee = models.ForeignKey(
        'Employee', on_delete=models.CASCADE, related_name='pending_hr_actions'
    )
    title = models.CharField(max_length=300)
    description = models.TextField()
    affected_overrides = models.JSONField(default=list)
    affected_requests = models.JSONField(default=list)
    suggested_actions = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='MEDIUM')
    resolved_by = models.ForeignKey(
        'Employee', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pending_hr_actions'
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(
                fields=['status', 'priority'], name='idx_hr_action_open',
                condition=models.Q(status='OPEN')
            ),
        ]

    def __str__(self):
        return f"[{self.priority}] {self.title}"
