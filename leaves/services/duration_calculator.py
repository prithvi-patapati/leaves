from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from leaves.models import CompanyConfig


def get_leave_year(target_date):
    config = CompanyConfig.get()
    start_month = config.leave_year_start_month
    if target_date.month >= start_month:
        return target_date.year
    return target_date.year - 1


def calculate_leave_days(start_date, end_date, is_half_day, employee=None):
    if is_half_day:
        return Decimal('0.5')

    config = CompanyConfig.get()
    weekend_days = set(config.weekend_days or [5, 6])

    working_days = 0
    current = start_date
    while current <= end_date:
        if current.weekday() not in weekend_days:
            working_days += 1
        current += timedelta(days=1)

    return Decimal(str(working_days))


def calculate_pro_rata_entitlement(entitlement_days, joining_date, leave_year_start):
    if joining_date <= leave_year_start:
        return entitlement_days

    leave_year_end = leave_year_start.replace(year=leave_year_start.year + 1) - timedelta(days=1)
    months_remaining = (leave_year_end.year - joining_date.year) * 12 + \
                       (leave_year_end.month - joining_date.month) + 1
    months_remaining = min(months_remaining, 12)

    pro_rata = (Decimal(str(entitlement_days)) * Decimal(str(months_remaining))) / Decimal('12')
    return pro_rata.quantize(Decimal('0.5'), rounding=ROUND_HALF_UP)
