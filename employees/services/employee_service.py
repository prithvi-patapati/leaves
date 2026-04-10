from datetime import date
from django.db import transaction
from employees.models import Employee, EmployeeChangeLog, PendingHRAction
from employees import signals
from .onboarding_service import apply_onboarding_templates


def _log_change(employee, field, old_val, new_val, actor, via='API'):
    EmployeeChangeLog.objects.create(
        employee=employee,
        field_changed=field,
        old_value=old_val,
        new_value=new_val,
        changed_by=actor,
        changed_via=via,
    )


@transaction.atomic
def add_employee(actor=None, via='API', **data):
    employee = Employee(**data)
    employee.save()
    onboarding_summary = apply_onboarding_templates(employee)

    PendingHRAction.objects.create(
        trigger_type='NEW_JOINER',
        employee=employee,
        title=f"New joiner: {employee.full_name} ({employee.employee_id}). Verify onboarding.",
        description=f"Templates applied: {', '.join(onboarding_summary) or 'None'}. Verify balances and overrides.",
        priority='LOW',
    )

    signals.employee_created.send(
        sender=Employee,
        employee_id=employee.employee_id,
        department=employee.department.code if employee.department else None,
        designation=employee.designation.title if employee.designation else None,
        manager=employee.reporting_manager_id,
        employment_type=employee.employment_type,
    )
    return employee, onboarding_summary


@transaction.atomic
def update_employee(actor, employee_id, via='API', **changes):
    employee = Employee.objects.select_for_update().get(employee_id=employee_id)
    leave_affecting = {'department', 'reporting_manager', 'designation', 'probation_status', 'is_active', 'teams'}

    for field, new_value in changes.items():
        old_value = getattr(employee, field)
        if field == 'teams':
            continue
        setattr(employee, field, new_value)
        _log_change(employee, field, str(old_value), str(new_value), actor, via)

        if field in leave_affecting:
            signals.employee_updated.send(
                sender=Employee,
                employee_id=employee.employee_id,
                field_changed=field,
                old_value=str(old_value),
                new_value=str(new_value),
            )

    employee.save()
    return employee


@transaction.atomic
def confirm_employee(actor, employee_id, via='API'):
    employee = Employee.objects.select_for_update().get(employee_id=employee_id)
    old_status = employee.probation_status
    employee.probation_status = 'CONFIRMED'
    employee.confirmation_date = date.today()
    employee.save()

    _log_change(employee, 'probation_status', old_status, 'CONFIRMED', actor, via)

    PendingHRAction.objects.create(
        trigger_type='CONFIRMATION',
        employee=employee,
        title=f"{employee.full_name} confirmed. Review probation overrides.",
        description=f"{employee.full_name} confirmed on {date.today()}. Check if probation-related overrides should be removed.",
        priority='MEDIUM',
    )

    signals.employee_confirmed.send(
        sender=Employee,
        employee_id=employee.employee_id,
        confirmation_date=str(date.today()),
    )
    return employee


@transaction.atomic
def deactivate_employee(actor, employee_id, last_working_date, exit_reason, via='API'):
    employee = Employee.objects.select_for_update().get(employee_id=employee_id)
    employee.is_active = False
    employee.last_working_date = last_working_date
    employee.exit_reason = exit_reason
    employee.save()

    _log_change(employee, 'is_active', 'True', 'False', actor, via)

    PendingHRAction.objects.create(
        trigger_type='EXIT',
        employee=employee,
        title=f"{employee.full_name} exited. Cancel pending requests and settle balances.",
        description=f"{employee.full_name} last working date: {last_working_date}. Exit reason: {exit_reason}.",
        priority='HIGH',
    )

    signals.employee_deactivated.send(
        sender=Employee,
        employee_id=employee.employee_id,
        last_working_date=str(last_working_date),
        exit_reason=exit_reason,
    )
    return employee


@transaction.atomic
def transfer_employee(actor, employee_id, via='API', department=None, reporting_manager=None, designation=None):
    employee = Employee.objects.select_for_update().get(employee_id=employee_id)
    old_dept = employee.department
    old_manager = employee.reporting_manager
    old_desg = employee.designation

    if department is not None:
        employee.department = department
        _log_change(employee, 'department', str(old_dept), str(department), actor, via)
    if reporting_manager is not None:
        employee.reporting_manager = reporting_manager
        _log_change(employee, 'reporting_manager', str(old_manager), str(reporting_manager), actor, via)
    if designation is not None:
        employee.designation = designation
        _log_change(employee, 'designation', str(old_desg), str(designation), actor, via)

    employee.save()

    signals.employee_transferred.send(
        sender=Employee,
        employee_id=employee.employee_id,
        old_department=str(old_dept),
        new_department=str(department) if department else str(old_dept),
        old_manager=str(old_manager),
        new_manager=str(reporting_manager) if reporting_manager else str(old_manager),
    )
    return employee


def get_employee(employee_id):
    return Employee.objects.select_related(
        'department', 'designation', 'reporting_manager'
    ).prefetch_related('teams').get(employee_id=employee_id)


def search_employees(department=None, team=None, designation=None, probation_status=None,
                     reporting_manager=None, name=None, is_active=True):
    qs = Employee.objects.filter(is_active=is_active).select_related('department', 'designation', 'reporting_manager')
    if department:
        qs = qs.filter(department__code=department)
    if team:
        qs = qs.filter(teams__code=team)
    if designation:
        qs = qs.filter(designation__title__icontains=designation)
    if probation_status:
        qs = qs.filter(probation_status=probation_status)
    if reporting_manager:
        qs = qs.filter(reporting_manager__employee_id=reporting_manager)
    if name:
        qs = qs.filter(full_name__icontains=name)
    return qs.distinct()
