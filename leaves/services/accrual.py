from datetime import date
from decimal import Decimal
from leaves.models import LeaveType, LeaveBalance, LeaveBalanceLedger
from employees.models import Employee
from .config_resolver import get_effective_config
from .duration_calculator import get_leave_year, calculate_pro_rata_entitlement


def run_monthly_accrual(execution_date=None):
    execution_date = execution_date or date.today()
    year = get_leave_year(execution_date)
    results = []

    monthly_types = LeaveType.objects.filter(credit_method='MONTHLY', is_active=True)

    for leave_type in monthly_types:
        for employee in Employee.objects.filter(is_active=True):
            already_accrued = LeaveBalanceLedger.objects.filter(
                employee=employee, leave_type=leave_type, year=year,
                txn_type='CREDIT_ACCRUAL',
                notes__contains=execution_date.strftime('%B %Y'),
            ).exists()

            if already_accrued:
                continue

            config = get_effective_config(employee, leave_type, execution_date)
            if config['block_accrual']:
                continue

            accrual_amount = leave_type.monthly_accrual_rate or Decimal('0.5')

            balance, _ = LeaveBalance.objects.get_or_create(
                employee=employee, leave_type=leave_type, year=year,
                defaults={'entitled': Decimal('0')}
            )

            if leave_type.carry_forward_max > 0:
                total_after = balance.available + accrual_amount
                if total_after > leave_type.carry_forward_max:
                    accrual_amount = max(
                        Decimal('0'),
                        Decimal(str(leave_type.carry_forward_max)) - balance.available
                    )

            if accrual_amount <= 0:
                continue

            balance.entitled += accrual_amount
            balance.save()

            LeaveBalanceLedger.objects.create(
                employee=employee, leave_type=leave_type, year=year,
                txn_type='CREDIT_ACCRUAL', days=accrual_amount,
                running_balance=balance.available,
                notes=f"Monthly accrual for {execution_date.strftime('%B %Y')}",
                actor=None, actor_channel='SYSTEM',
            )
            results.append({'employee': employee.employee_id, 'type': leave_type.code, 'days': str(accrual_amount)})

    return results


def run_bulk_credit(year, leave_type_code=None):
    types_qs = LeaveType.objects.filter(credit_method='BULK', is_active=True)
    if leave_type_code:
        types_qs = types_qs.filter(code=leave_type_code)

    leave_year_start = date(year, 4, 1)  # TODO: read from CompanyConfig
    results = []

    for leave_type in types_qs:
        for employee in Employee.objects.filter(is_active=True):
            already_credited = LeaveBalanceLedger.objects.filter(
                employee=employee, leave_type=leave_type, year=year,
                txn_type='CREDIT_BULK',
            ).exists()
            if already_credited:
                continue

            config = get_effective_config(employee, leave_type, leave_year_start)

            entitlement = config['entitlement_days']
            if leave_type.is_pro_rata:
                entitlement = calculate_pro_rata_entitlement(
                    entitlement, employee.date_of_joining, leave_year_start
                )

            entitlement = Decimal(str(entitlement))
            if entitlement <= 0:
                continue

            balance, _ = LeaveBalance.objects.get_or_create(
                employee=employee, leave_type=leave_type, year=year,
                defaults={'entitled': Decimal('0')}
            )
            balance.entitled += entitlement
            balance.save()

            LeaveBalanceLedger.objects.create(
                employee=employee, leave_type=leave_type, year=year,
                txn_type='CREDIT_BULK', days=entitlement,
                running_balance=balance.available,
                notes=f"Bulk credit for year {year}",
                actor=None, actor_channel='SYSTEM',
            )
            results.append({'employee': employee.employee_id, 'type': leave_type.code, 'days': str(entitlement)})

    return results
