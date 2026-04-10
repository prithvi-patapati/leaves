from django.db import models


class OnboardingTemplate(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    match_department = models.ForeignKey(
        'Department', null=True, blank=True, on_delete=models.SET_NULL
    )
    match_team = models.ForeignKey(
        'Team', null=True, blank=True, on_delete=models.SET_NULL
    )
    match_designation = models.ForeignKey(
        'Designation', null=True, blank=True, on_delete=models.SET_NULL
    )
    match_employment_type = models.CharField(max_length=20, blank=True)
    priority = models.IntegerField(default=10)
    actions = models.JSONField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'Employee', null=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'onboarding_templates'
        ordering = ['priority']

    def __str__(self):
        return self.name
