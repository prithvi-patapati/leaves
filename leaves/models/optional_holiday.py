from django.db import models


class OptionalHoliday(models.Model):
    name = models.CharField(max_length=200)
    date = models.DateField()
    year = models.IntegerField(db_index=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'employees.Employee', null=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'optional_holidays'
        ordering = ['date']
        unique_together = ('name', 'year')

    def __str__(self):
        return f"{self.name} ({self.date})"


class OptionalHolidaySelection(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='optional_holiday_selections'
    )
    holiday = models.ForeignKey(OptionalHoliday, on_delete=models.CASCADE, related_name='selections')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    approved_by = models.ForeignKey(
        'employees.Employee', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'optional_holiday_selections'
        unique_together = ('employee', 'holiday')

    def __str__(self):
        return f"{self.employee} - {self.holiday.name}"
