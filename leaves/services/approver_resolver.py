from datetime import date
from django.db import models
from employees.models import Employee
from leaves.models import LeaveRequest, FallbackManager, CompanyConfig


def get_hr_head():
    return Employee.objects.filter(
        designation__title__icontains='Senior HR Manager',
        is_active=True
    ).first() or Employee.objects.filter(
        department__code='HR',
        is_active=True
    ).order_by('-designation__level').first()


def get_ceo():
    return Employee.objects.filter(
        reporting_manager__isnull=True,
        is_active=True
    ).order_by('-designation__level').first()


def determine_approver(employee, leave_type, config):
    chain = config.get('approval_chain', [])

    if not chain:
        return None

    first_step = chain[0]

    if first_step == 'REPORTING_MANAGER':
        manager = employee.reporting_manager

        if manager is None:
            company = CompanyConfig.get()
            if company.top_level_approval_mode == 'SELF_APPROVE_WITH_HR_NOTIFY':
                return employee
            elif company.top_level_approval_mode == 'ESCALATE_TO_HR':
                return get_hr_head()
            elif company.top_level_approval_mode == 'ESCALATE_TO_CEO':
                return get_ceo()

        # Check if manager is on leave today
        if manager:
            manager_on_leave = LeaveRequest.objects.filter(
                employee=manager,
                status='APPROVED',
                start_date__lte=date.today(),
                end_date__gte=date.today(),
            ).exists()

            if manager_on_leave:
                fallback = FallbackManager.objects.filter(
                    employee=employee,
                    primary_manager=manager,
                    is_active=True,
                    effective_from__lte=date.today(),
                ).filter(
                    models.Q(effective_to__gte=date.today()) |
                    models.Q(effective_to__isnull=True)
                ).first()

                if fallback:
                    return fallback.fallback_manager
                else:
                    return get_hr_head()

            return manager

    elif first_step == 'HR':
        return get_hr_head()

    elif first_step == 'SELF_APPROVE_WITH_HR_NOTIFY':
        return employee

    return None
