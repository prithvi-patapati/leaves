from django.dispatch import receiver
from employees.signals import (
    employee_confirmed, employee_deactivated, employee_transferred,
    team_membership_changed,
)
from leaves.services.hr_action_service import create_nudge


@receiver(employee_transferred)
def on_employee_transferred(sender, **kwargs):
    from employees.models import Employee
    emp_id = kwargs.get('employee_id')
    if not emp_id:
        return
    try:
        employee = Employee.objects.get(employee_id=emp_id)
    except Employee.DoesNotExist:
        return

    old_dept = kwargs.get('old_department', '')
    new_dept = kwargs.get('new_department', '')

    from leaves.models import EmployeeOverride
    active_overrides = EmployeeOverride.objects.filter(employee=employee, is_active=True)
    if active_overrides.exists():
        create_nudge(
            trigger_type='DEPARTMENT_CHANGE',
            employee=employee,
            title=f"{employee.full_name} moved from {old_dept} to {new_dept} — {active_overrides.count()} active overrides may need review",
            description=f"Review overrides after department transfer.",
            priority='MEDIUM',
        )


@receiver(employee_confirmed)
def on_employee_confirmed(sender, **kwargs):
    from employees.models import Employee
    emp_id = kwargs.get('employee_id')
    if not emp_id:
        return
    try:
        employee = Employee.objects.get(employee_id=emp_id)
    except Employee.DoesNotExist:
        return

    create_nudge(
        trigger_type='CONFIRMATION',
        employee=employee,
        title=f"{employee.full_name} confirmed. Review probation overrides.",
        description=f"Check if any probation-related overrides should be removed.",
        priority='MEDIUM',
    )


@receiver(employee_deactivated)
def on_employee_deactivated(sender, **kwargs):
    from employees.models import Employee
    emp_id = kwargs.get('employee_id')
    if not emp_id:
        return
    try:
        employee = Employee.objects.get(employee_id=emp_id)
    except Employee.DoesNotExist:
        return

    from leaves.models import LeaveRequest
    pending = LeaveRequest.objects.filter(employee=employee, status='PENDING').count()

    create_nudge(
        trigger_type='EXIT',
        employee=employee,
        title=f"{employee.full_name} exited. {pending} pending requests need cancellation.",
        description=f"Cancel pending requests and settle final balances.",
        priority='HIGH',
    )
