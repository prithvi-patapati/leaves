from datetime import date
from django.db import models
from leaves.models import EmployeeOverride


def get_effective_config(employee, leave_type, target_date=None):
    target_date = target_date or date.today()

    config = {
        'entitlement_days': leave_type.entitlement_days,
        'credit_method': leave_type.credit_method,
        'monthly_accrual_rate': leave_type.monthly_accrual_rate,
        'half_day_allowed': leave_type.half_day_allowed,
        'advance_notice_days': leave_type.advance_notice_days,
        'can_apply_in_advance': leave_type.can_apply_in_advance,
        'can_apply_retroactively': leave_type.can_apply_retroactively,
        'document_required': leave_type.document_required,
        'document_required_after_days': leave_type.document_required_after_days,
        'gender_restriction': leave_type.gender_restriction,
        'min_service_days': leave_type.min_service_days,
        'avail_window_days': leave_type.avail_window_days,
        'probation_eligible': leave_type.probation_eligible,
        'consecutive_day_restriction': leave_type.consecutive_day_restriction,
        'max_continuous_days_before_flag': leave_type.max_continuous_days_before_flag,
        'approval_chain': leave_type.approval_chain,
        'block_accrual': False,
        'block_application': False,
        'block_approval': False,
    }

    overrides = EmployeeOverride.objects.filter(
        employee=employee,
        is_active=True,
        effective_from__lte=target_date,
    ).filter(
        models.Q(effective_to__gte=target_date) | models.Q(effective_to__isnull=True)
    ).filter(
        models.Q(leave_type=leave_type) | models.Q(leave_type__isnull=True)
    ).order_by('-created_at')

    entitlement_set = False
    chain_set = False
    waived_keys = set()

    for override in overrides:
        if override.block_accrual:
            config['block_accrual'] = True
        if override.block_application:
            config['block_application'] = True
        if override.block_approval:
            config['block_approval'] = True
        if override.modify_entitlement is not None and not entitlement_set:
            config['entitlement_days'] = override.modify_entitlement
            entitlement_set = True
        if override.custom_approval_chain and not chain_set:
            config['approval_chain'] = override.custom_approval_chain
            chain_set = True
        for key, value in override.waive_restriction.items():
            if key in config and key not in waived_keys:
                config[key] = value
                waived_keys.add(key)

    return config
