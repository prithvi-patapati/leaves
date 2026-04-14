from datetime import date
from leaves.models import FallbackManager
from employees.models import Employee


def set_fallback(actor, employee_id, primary_manager_id, fallback_manager_id,
                 effective_from=None, effective_to=None, reason=''):
    return FallbackManager.objects.create(
        employee=Employee.objects.get(employee_id=employee_id),
        primary_manager=Employee.objects.get(employee_id=primary_manager_id),
        fallback_manager=Employee.objects.get(employee_id=fallback_manager_id),
        effective_from=effective_from or date.today(),
        effective_to=effective_to,
        reason=reason,
        created_by=actor,
    )


def get_fallback_managers(employee_id=None, active_only=True):
    qs = FallbackManager.objects.select_related('employee', 'primary_manager', 'fallback_manager')
    if employee_id:
        emp = Employee.objects.get(employee_id=employee_id)
        qs = qs.filter(employee=emp)
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.order_by('-created_at')
