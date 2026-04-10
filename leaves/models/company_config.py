from django.db import models


class CompanyConfig(models.Model):
    leave_year_start_month = models.IntegerField(default=4)
    leave_year_start_day = models.IntegerField(default=1)
    working_days_per_week = models.IntegerField(default=5)
    weekend_days = models.JSONField(default=list)
    max_optional_holidays_per_year = models.IntegerField(default=3)
    top_level_approval_mode = models.CharField(max_length=30, choices=[
        ('SELF_APPROVE_WITH_HR_NOTIFY', 'CEO self-approves, HR notified'),
        ('ESCALATE_TO_HR', 'Goes to HR head'),
        ('ESCALATE_TO_CEO', 'Goes to CEO'),
    ], default='SELF_APPROVE_WITH_HR_NOTIFY')

    class Meta:
        db_table = 'company_config'

    def __str__(self):
        return "Company Config"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={'weekend_days': [5, 6]})
        return obj
