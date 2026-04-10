from django.db import models


class PayrollAdjustmentPending(models.Model):
    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='payroll_adjustments'
    )
    adjustment_type = models.CharField(max_length=30, choices=[
        ('LOP_DEDUCTION', 'LOP salary deduction'),
        ('LEAVE_ENCASHMENT', 'Leave encashment payout'),
    ])
    amount_description = models.TextField()
    reference_request = models.ForeignKey(
        'LeaveRequest', null=True, blank=True, on_delete=models.SET_NULL
    )
    is_processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payroll_adjustments_pending'

    def __str__(self):
        return f"{self.employee} - {self.adjustment_type}"
