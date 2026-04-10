from django.db import models


class LeaveBalance(models.Model):
    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='leave_balances'
    )
    leave_type = models.ForeignKey('LeaveType', on_delete=models.CASCADE, related_name='balances')
    year = models.IntegerField()

    entitled = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    used = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    pending = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    carried_forward = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    converted_in = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    adjusted = models.DecimalField(max_digits=6, decimal_places=1, default=0)
    lapsed = models.DecimalField(max_digits=6, decimal_places=1, default=0)

    @property
    def available(self):
        return (
            self.entitled + self.carried_forward + self.converted_in + self.adjusted
            - self.used - self.pending
        )

    @property
    def total_credited(self):
        return self.entitled + self.carried_forward + self.converted_in + self.adjusted

    class Meta:
        db_table = 'leave_balances'
        unique_together = ('employee', 'leave_type', 'year')
        indexes = [
            models.Index(fields=['employee', 'year'], name='idx_balance_emp_year'),
        ]

    def __str__(self):
        return f"{self.employee} - {self.leave_type} ({self.year})"


class LeaveBalanceLedger(models.Model):
    TXN_TYPES = [
        ('CREDIT_BULK', 'Bulk credit at year start'),
        ('CREDIT_ACCRUAL', 'Monthly accrual'),
        ('CREDIT_CARRY_FWD', 'Carry forward from previous year'),
        ('CREDIT_CONVERSION', 'Converted from another leave type'),
        ('CREDIT_ADJUSTMENT', 'Manual adjustment by HR (positive)'),
        ('CREDIT_REVERSAL', 'Reversal due to leave cancellation'),
        ('DEBIT_APPROVED', 'Leave approved — balance consumed'),
        ('DEBIT_ADJUSTMENT', 'Manual adjustment by HR (negative)'),
        ('HOLD_PENDING', 'Balance held for pending request'),
        ('RELEASE_HOLD', 'Hold released — request rejected/cancelled'),
        ('LAPSE', 'Year-end lapse of unused balance'),
        ('CONVERSION_OUT', 'Converted out to another leave type'),
    ]
    ACTOR_CHANNELS = [
        ('SYSTEM', 'Automated by engine'),
        ('AGENT', 'Via chatbot/agent'),
        ('DASHBOARD', 'Via web dashboard'),
        ('API', 'Via direct API call'),
    ]

    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='leave_ledger'
    )
    leave_type = models.ForeignKey('LeaveType', on_delete=models.CASCADE, related_name='ledger_entries')
    year = models.IntegerField()
    txn_type = models.CharField(max_length=30, choices=TXN_TYPES)
    days = models.DecimalField(max_digits=6, decimal_places=1)
    running_balance = models.DecimalField(max_digits=6, decimal_places=1)
    reference_request = models.ForeignKey(
        'LeaveRequest', null=True, blank=True, on_delete=models.SET_NULL
    )
    notes = models.TextField(blank=True)
    actor = models.ForeignKey(
        'employees.Employee', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    actor_channel = models.CharField(max_length=20, choices=ACTOR_CHANNELS, default='SYSTEM')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'leave_balance_ledger'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['employee', 'leave_type', 'year'], name='idx_ledger_emp_type_year'),
        ]

    def __str__(self):
        return f"{self.txn_type}: {self.days} days"
