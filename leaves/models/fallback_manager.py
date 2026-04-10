from django.db import models


class FallbackManager(models.Model):
    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='fallback_managers'
    )
    primary_manager = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='fallback_from'
    )
    fallback_manager = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='fallback_to'
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    reason = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'employees.Employee', null=True, on_delete=models.SET_NULL, related_name='+'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fallback_managers'

    def __str__(self):
        return f"Fallback for {self.employee}: {self.primary_manager} → {self.fallback_manager}"
