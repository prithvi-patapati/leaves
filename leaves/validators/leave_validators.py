from datetime import date, timedelta
from decimal import Decimal
from django.db import models
from leaves.models import LeaveRequest


def validate_employee_active(employee, leave_type, request_data, config):
    if not employee.is_active:
        return False, "Employee is not active."
    return True, None


def validate_leave_type_active(employee, leave_type, request_data, config):
    if not leave_type.is_active:
        return False, f"Leave type {leave_type.code} is not active."
    return True, None


def validate_not_blocked_by_override(employee, leave_type, request_data, config):
    if config.get('block_application'):
        return False, f"Leave application is blocked for {leave_type.code} by an active override."
    return True, None


def validate_gender_eligibility(employee, leave_type, request_data, config):
    restriction = config.get('gender_restriction')
    if restriction and employee.gender != restriction:
        return False, f"{leave_type.name} is restricted to gender '{restriction}'."
    return True, None


def validate_probation_eligibility(employee, leave_type, request_data, config):
    if not config.get('probation_eligible', True) and employee.is_on_probation:
        return False, f"{leave_type.name} is not available during probation."
    return True, None


def validate_min_service_days(employee, leave_type, request_data, config):
    min_days = config.get('min_service_days', 0)
    if min_days and employee.service_days < min_days:
        return False, f"Minimum {min_days} days of service required. You have {employee.service_days}."
    return True, None


def validate_avail_window(employee, leave_type, request_data, config):
    window = config.get('avail_window_days')
    event_date = request_data.get('event_date')
    if window and event_date:
        deadline = event_date + timedelta(days=window)
        if request_data['start_date'] > deadline:
            return False, f"Must be availed within {window} days of the event ({event_date})."
    return True, None


def validate_advance_notice(employee, leave_type, request_data, config):
    notice_days = config.get('advance_notice_days', 0)
    if notice_days > 0:
        days_before = (request_data['start_date'] - date.today()).days
        if days_before < notice_days:
            return False, f"Minimum {notice_days} days advance notice required."
    return True, None


def validate_advance_application_policy(employee, leave_type, request_data, config):
    if not config.get('can_apply_in_advance', True):
        if request_data['start_date'] > date.today():
            return False, f"{leave_type.name} cannot be applied in advance."
    return True, None


def validate_retroactive_policy(employee, leave_type, request_data, config):
    if not config.get('can_apply_retroactively', False):
        if request_data['end_date'] < date.today():
            return False, f"{leave_type.name} cannot be applied retroactively."
    return True, None


def validate_balance_sufficient(employee, leave_type, request_data, config):
    if leave_type.credit_method in ('ON_DEMAND', 'EVENT'):
        return True, None

    from leaves.models import LeaveBalance
    from leaves.services.duration_calculator import get_leave_year

    year = get_leave_year(request_data['start_date'])
    try:
        balance = LeaveBalance.objects.get(
            employee=employee, leave_type=leave_type, year=year
        )
        if balance.available < request_data['duration']:
            return False, f"Insufficient balance. Available: {balance.available}, requested: {request_data['duration']}."
    except LeaveBalance.DoesNotExist:
        return False, f"No balance found for {leave_type.code} in year {year}."
    return True, None


def validate_half_day_rules(employee, leave_type, request_data, config):
    if request_data.get('is_half_day'):
        if not config.get('half_day_allowed', True):
            return False, f"Half-day is not allowed for {leave_type.name}."
        if request_data['start_date'] != request_data['end_date']:
            return False, "Half-day leave must be for a single day."
        if not request_data.get('half_day_period'):
            return False, "Half-day period (AM/PM) must be specified."
    return True, None


def validate_document_requirement(employee, leave_type, request_data, config):
    if config.get('document_required'):
        after_days = config.get('document_required_after_days', 0)
        if after_days == 0 and not request_data.get('document'):
            return False, f"Document is required for {leave_type.name}."
        elif after_days > 0 and request_data['duration'] > Decimal(str(after_days)):
            if not request_data.get('document'):
                return False, f"Document required for {leave_type.name} exceeding {after_days} days."
    return True, None


def validate_consecutive_restriction(employee, leave_type, request_data, config):
    if not config.get('consecutive_day_restriction'):
        return True, None

    start = request_data['start_date']
    prev_day = start - timedelta(days=1)
    while prev_day.weekday() in (5, 6):
        prev_day -= timedelta(days=1)

    has_adjacent = LeaveRequest.objects.filter(
        employee=employee,
        leave_type=leave_type,
        status__in=['PENDING', 'APPROVED'],
    ).filter(
        models.Q(end_date=prev_day) | models.Q(start_date=request_data['end_date'] + timedelta(days=1))
    ).exists()

    if has_adjacent:
        return False, f"Consecutive {leave_type.name} days are restricted."
    return True, None


def validate_overlapping_requests(employee, leave_type, request_data, config):
    start = request_data['start_date']
    end = request_data['end_date']
    is_half_day = request_data.get('is_half_day', False)
    half_day_period = request_data.get('half_day_period')

    overlapping = LeaveRequest.objects.filter(
        employee=employee,
        status__in=['PENDING', 'APPROVED'],
        start_date__lte=end,
        end_date__gte=start,
    )

    for req in overlapping:
        if is_half_day and req.is_half_day:
            if start == req.start_date and half_day_period != req.half_day_period:
                continue
        return False, f"Overlapping leave request exists (#{req.id})."
    return True, None


def validate_company_holiday_overlap(employee, leave_type, request_data, config):
    # Skip for now — no CompanyHoliday model defined
    return True, None


def validate_weekend_only_check(employee, leave_type, request_data, config):
    if request_data['duration'] <= 0 and not request_data.get('is_half_day'):
        return False, "Selected dates fall entirely on weekends/holidays."
    return True, None


VALIDATORS = [
    validate_employee_active,
    validate_leave_type_active,
    validate_not_blocked_by_override,
    validate_gender_eligibility,
    validate_probation_eligibility,
    validate_min_service_days,
    validate_avail_window,
    validate_advance_notice,
    validate_advance_application_policy,
    validate_retroactive_policy,
    validate_balance_sufficient,
    validate_half_day_rules,
    validate_document_requirement,
    validate_consecutive_restriction,
    validate_overlapping_requests,
    validate_company_holiday_overlap,
    validate_weekend_only_check,
]


def run_validators(employee, leave_type, request_data, config):
    for validator in VALIDATORS:
        passed, error = validator(employee, leave_type, request_data, config)
        if not passed:
            return False, error
    return True, None
