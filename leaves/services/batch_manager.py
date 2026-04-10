from datetime import date
from django.db import transaction
from django.utils import timezone
from employees.models import Employee
from leaves.models import BatchOperation, EmployeeOverride, LeaveType


@transaction.atomic
def bulk_create_overrides(actor, filter_criteria, override_template, idempotency_key=None):
    employees = _filter_employees(filter_criteria)
    batch = BatchOperation.objects.create(
        action_type='CREATE_OVERRIDE',
        filter_criteria=filter_criteria,
        template=override_template,
        affected_count=employees.count(),
        affected_employees=[e.employee_id for e in employees],
        status='PENDING_CONFIRMATION',
        created_by=actor,
    )
    return batch


@transaction.atomic
def confirm_batch(actor, batch_id, idempotency_key=None):
    batch = BatchOperation.objects.select_for_update().get(id=batch_id)
    if batch.status != 'PENDING_CONFIRMATION':
        raise ValueError(f"Batch is not pending confirmation (status: {batch.status}).")

    leave_type = None
    if batch.template.get('leave_type_code'):
        leave_type = LeaveType.objects.get(code=batch.template['leave_type_code'])

    for emp_id in batch.affected_employees:
        employee = Employee.objects.get(employee_id=emp_id)
        EmployeeOverride.objects.create(
            employee=employee,
            leave_type=leave_type,
            block_accrual=batch.template.get('block_accrual', False),
            block_application=batch.template.get('block_application', False),
            block_approval=batch.template.get('block_approval', False),
            modify_entitlement=batch.template.get('modify_entitlement'),
            waive_restriction=batch.template.get('waive_restriction', {}),
            custom_approval_chain=batch.template.get('custom_approval_chain', []),
            effective_from=batch.template.get('effective_from', date.today()),
            effective_to=batch.template.get('effective_to'),
            reason=batch.template.get('reason', 'Bulk operation'),
            created_by=actor,
            created_via='API',
            batch_id=batch,
        )

    batch.status = 'EXECUTED'
    batch.executed_at = timezone.now()
    batch.save()
    return batch


@transaction.atomic
def rollback_batch(actor, batch_id, reason, idempotency_key=None):
    batch = BatchOperation.objects.select_for_update().get(id=batch_id)
    if batch.status != 'EXECUTED':
        raise ValueError(f"Can only rollback executed batches (status: {batch.status}).")

    EmployeeOverride.objects.filter(batch_id=batch).update(is_active=False)
    batch.status = 'ROLLED_BACK'
    batch.rolled_back_at = timezone.now()
    batch.save()
    return batch


def _filter_employees(criteria):
    qs = Employee.objects.filter(is_active=True)
    if criteria.get('department'):
        qs = qs.filter(department__code=criteria['department'])
    if criteria.get('is_on_probation'):
        qs = qs.filter(probation_status='ON_PROBATION')
    if criteria.get('team'):
        qs = qs.filter(teams__code=criteria['team'])
    if criteria.get('employment_type'):
        qs = qs.filter(employment_type=criteria['employment_type'])
    return qs
