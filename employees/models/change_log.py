from django.db import models


class EmployeeChangeLog(models.Model):
    CHANGED_VIA_CHOICES = [
        ('AGENT', 'Via chatbot/agent'),
        ('DASHBOARD', 'Via web dashboard'),
        ('ADMIN', 'Via Django admin'),
        ('API', 'Via direct API call'),
        ('IMPORT', 'Via bulk import'),
    ]

    employee = models.ForeignKey(
        'Employee', on_delete=models.CASCADE, related_name='change_logs'
    )
    field_changed = models.CharField(max_length=50)
    old_value = models.JSONField(null=True)
    new_value = models.JSONField(null=True)
    changed_by = models.ForeignKey(
        'Employee', on_delete=models.SET_NULL, null=True, related_name='+'
    )
    changed_via = models.CharField(max_length=20, choices=CHANGED_VIA_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'employee_change_logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.employee} - {self.field_changed}"
