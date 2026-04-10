from datetime import date
from django.db import models, transaction
from leaves.models import LeaveType, EmployeeOverride
from employees.models import Employee


@transaction.atomic
def create_override(actor, employee_id, leave_type_code=None, via='API', **fields):
    employee = Employee.objects.get(employee_id=employee_id)
    leave_type = LeaveType.objects.get(code=leave_type_code) if leave_type_code else None

    conflicts = check_override_conflict(
        employee, leave_type,
        fields.get('effective_from', date.today()),
        fields.get('effective_to'),
    )
    if conflicts:
        raise ValueError(f"Conflicting override(s) exist: {[o.id for o in conflicts]}")

    override = EmployeeOverride.objects.create(
        employee=employee,
        leave_type=leave_type,
        created_by=actor,
        created_via=via,
        **fields,
    )
    return override


@transaction.atomic
def remove_override(actor, override_id, reason=None):
    override = EmployeeOverride.objects.get(id=override_id)
    override.is_active = False
    if reason:
        override.reason += f"\n[Deactivated: {reason}]"
    override.save()
    return override


def check_override_conflict(employee, leave_type, effective_from, effective_to):
    qs = EmployeeOverride.objects.filter(
        employee=employee,
        is_active=True,
        effective_from__lte=effective_to if effective_to else date(9999, 12, 31),
    ).filter(
        models.Q(effective_to__gte=effective_from) | models.Q(effective_to__isnull=True)
    ).filter(
        models.Q(leave_type=leave_type) | models.Q(leave_type__isnull=True)
    )
    if leave_type is None:
        qs = qs.filter(leave_type__isnull=True)
    return list(qs)


def get_overrides(employee_id=None, leave_type_code=None, active_only=True):
    qs = EmployeeOverride.objects.all()
    if employee_id:
        qs = qs.filter(employee__employee_id=employee_id)
    if leave_type_code:
        qs = qs.filter(leave_type__code=leave_type_code)
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.select_related('employee', 'leave_type')
