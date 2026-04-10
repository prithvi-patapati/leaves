from datetime import date
from django.db import models


class Employee(models.Model):
    EMPLOYMENT_TYPES = [
        ('FULL_TIME', 'Full-time employee'),
        ('INTERN', 'Intern'),
        ('CONTRACT', 'Contractor'),
        ('CONSULTANT', 'Consultant'),
    ]
    PROBATION_STATUSES = [
        ('ON_PROBATION', 'On probation'),
        ('CONFIRMED', 'Confirmed'),
        ('NOTICE_PERIOD', 'On notice period'),
    ]
    EXIT_REASONS = [
        ('RESIGNED', 'Resigned'),
        ('TERMINATED', 'Terminated'),
        ('CONTRACT_END', 'Contract ended'),
        ('INTERNSHIP_END', 'Internship ended'),
    ]
    GENDER_CHOICES = [
        ('M', 'Male'), ('F', 'Female'), ('O', 'Other'),
    ]

    # Identity
    employee_id = models.CharField(max_length=20, unique=True, db_index=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    full_name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    date_of_birth = models.DateField(null=True, blank=True)

    # Organizational
    department = models.ForeignKey(
        'Department', on_delete=models.PROTECT, related_name='employees'
    )
    designation = models.ForeignKey(
        'Designation', on_delete=models.PROTECT, related_name='employees'
    )
    teams = models.ManyToManyField('Team', blank=True, related_name='members')
    reporting_manager = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='direct_reports'
    )

    # Employment Status
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPES, default='FULL_TIME')
    date_of_joining = models.DateField()
    probation_status = models.CharField(max_length=20, choices=PROBATION_STATUSES, default='ON_PROBATION')
    probation_end_date = models.DateField(null=True, blank=True)
    confirmation_date = models.DateField(null=True, blank=True)

    # Exit
    is_active = models.BooleanField(default=True)
    last_working_date = models.DateField(null=True, blank=True)
    exit_reason = models.CharField(max_length=30, blank=True, choices=EXIT_REASONS)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+'
    )

    class Meta:
        db_table = 'employees'
        ordering = ['employee_id']
        indexes = [
            models.Index(fields=['department', 'is_active'], name='idx_emp_dept_active'),
            models.Index(fields=['reporting_manager', 'is_active'], name='idx_emp_manager_active'),
            models.Index(fields=['probation_status'], name='idx_emp_probation'),
        ]

    def save(self, *args, **kwargs):
        self.full_name = f"{self.first_name} {self.last_name}".strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee_id} - {self.full_name}"

    @property
    def is_on_probation(self):
        return self.probation_status == 'ON_PROBATION'

    @property
    def service_days(self):
        return (date.today() - self.date_of_joining).days
