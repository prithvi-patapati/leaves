from django.db import models


class Activity(models.Model):
    """Every significant event in the system. The single source of truth for what happened."""

    EVENT_TYPES = [
        ('LEAVE_APPLIED', 'Leave Applied'),
        ('LEAVE_APPROVED', 'Leave Approved'),
        ('LEAVE_REJECTED', 'Leave Rejected'),
        ('LEAVE_CANCELLED', 'Leave Cancelled'),
        ('BALANCE_ADJUSTED', 'Balance Adjusted'),
        ('POLICY_CHANGED', 'Policy Changed'),
        ('OVERRIDE_CREATED', 'Override Created'),
        ('OVERRIDE_REMOVED', 'Override Removed'),
        ('EMPLOYEE_ADDED', 'Employee Added'),
        ('EMPLOYEE_CONFIRMED', 'Employee Confirmed'),
        ('EMPLOYEE_DEACTIVATED', 'Employee Deactivated'),
        ('EMPLOYEE_TRANSFERRED', 'Employee Transferred'),
    ]

    VISIBILITY_CHOICES = [
        ('ALL', 'Everyone'),
        ('HR', 'HR Only'),
        ('MANAGER', 'Manager + HR'),
        ('EMPLOYEE', 'Employee + Manager + HR'),
    ]

    event_type = models.CharField(max_length=30, choices=EVENT_TYPES)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default='')

    # Who did this
    actor_id = models.CharField(max_length=20, blank=True, default='',
                                help_text='Employee ID of who performed the action')
    actor_name = models.CharField(max_length=200, blank=True, default='')

    # Who is it about
    target_id = models.CharField(max_length=20, blank=True, default='',
                                 help_text='Employee ID of who is affected')
    target_name = models.CharField(max_length=200, blank=True, default='')

    # Who should see this
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='EMPLOYEE')

    # For manager filtering — which manager's team does this belong to
    manager_id = models.CharField(max_length=20, blank=True, default='',
                                  help_text='Reporting manager employee ID (for manager feed filtering)')

    # Extra data (leave type, dates, etc.)
    metadata = models.JSONField(default=dict, blank=True)

    # Channels — tracks where this notification was "sent" (for now just logged)
    channels = models.JSONField(default=list, blank=True,
                                help_text='List of channels: ["web", "slack_dm", "email"]')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications_activity'
        ordering = ['-created_at']
        verbose_name = 'Activity'
        verbose_name_plural = 'Activities'

    def __str__(self):
        return f"[{self.event_type}] {self.title}"
