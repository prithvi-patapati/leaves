from decimal import Decimal
from django.db import transaction
from leaves.models import LeaveBalance, LeaveBalanceLedger, LeaveType
from leaves import signals
from .duration_calculator import get_leave_year


@transaction.atomic
def credit_balance(employee, leave_type, year, days, txn_type, notes='', actor=None, channel='SYSTEM'):
    balance, _ = LeaveBalance.objects.get_or_create(
        employee=employee, leave_type=leave_type, year=year,
        defaults={'entitled': Decimal('0')}
    )

    days = Decimal(str(days))

    if txn_type in ('CREDIT_BULK', 'CREDIT_ACCRUAL', 'CREDIT_ADJUSTMENT'):
        balance.entitled += days
    elif txn_type == 'CREDIT_CARRY_FWD':
        balance.carried_forward += days
    elif txn_type == 'CREDIT_CONVERSION':
        balance.converted_in += days
    elif txn_type == 'CREDIT_REVERSAL':
        balance.used -= days
    balance.save()

    LeaveBalanceLedger.objects.create(
        employee=employee, leave_type=leave_type, year=year,
        txn_type=txn_type, days=days, running_balance=balance.available,
        notes=notes, actor=actor, actor_channel=channel,
    )
    return balance


@transaction.atomic
def adjust_balance(actor, employee_id, leave_type_code, days, reason, idempotency_key=None):
    from employees.models import Employee
    from .idempotency import execute_with_idempotency

    def _do():
        employee = Employee.objects.get(employee_id=employee_id)
        leave_type = LeaveType.objects.get(code=leave_type_code)
        year = get_leave_year(__import__('datetime').date.today())
        days_dec = Decimal(str(days))

        balance, _ = LeaveBalance.objects.get_or_create(
            employee=employee, leave_type=leave_type, year=year,
            defaults={'entitled': Decimal('0')}
        )

        if days_dec >= 0:
            txn_type = 'CREDIT_ADJUSTMENT'
        else:
            txn_type = 'DEBIT_ADJUSTMENT'

        balance.adjusted += days_dec
        balance.save()

        LeaveBalanceLedger.objects.create(
            employee=employee, leave_type=leave_type, year=year,
            txn_type=txn_type, days=days_dec, running_balance=balance.available,
            notes=reason, actor=actor, actor_channel='AGENT',
        )

        signals.balance_adjusted.send(
            sender=LeaveBalance,
            employee_id=employee_id,
            leave_type=leave_type_code,
            days=str(days_dec),
            reason=reason,
            adjusted_by=actor.employee_id if actor else None,
        )
        return balance

    return execute_with_idempotency(
        idempotency_key, 'adjust_balance',
        {'employee_id': employee_id, 'leave_type': leave_type_code, 'days': str(days)},
        _do
    )


def get_balances(employee_id, year=None):
    from employees.models import Employee
    from datetime import date
    employee = Employee.objects.get(employee_id=employee_id)
    if year is None:
        year = get_leave_year(date.today())
    return LeaveBalance.objects.filter(
        employee=employee, year=year
    ).select_related('leave_type')


def get_team_balances(actor):
    from employees.models import Employee
    from datetime import date
    reports = Employee.objects.filter(reporting_manager=actor, is_active=True)
    year = get_leave_year(date.today())
    return LeaveBalance.objects.filter(
        employee__in=reports, year=year
    ).select_related('employee', 'leave_type')
