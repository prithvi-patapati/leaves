from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from leaves.models import LeaveRequest, LeaveBalance, LeaveBalanceLedger
from employees.models import PendingHRAction
from leaves import signals
from .config_resolver import get_effective_config
from .duration_calculator import get_leave_year


@transaction.atomic
def approve_leave(approver, request_id, remarks='', idempotency_key=None):
    from .idempotency import execute_with_idempotency

    def _do():
        request = LeaveRequest.objects.select_for_update().get(id=request_id)

        if request.status != 'PENDING':
            raise ValueError(f"Request is not pending (status: {request.status}).")

        if request.current_approver_id != approver.id:
            raise ValueError("You are not the current approver for this request.")

        config = get_effective_config(request.employee, request.leave_type)
        if config.get('block_approval'):
            raise ValueError("Approval is blocked by an active override.")

        year = get_leave_year(request.start_date)

        # Move from pending to used
        if request.leave_type.credit_method not in ('ON_DEMAND', 'EVENT'):
            balance = LeaveBalance.objects.get(
                employee=request.employee, leave_type=request.leave_type, year=year
            )
            balance.pending -= request.duration_days
            balance.used += request.duration_days
            balance.save()

            LeaveBalanceLedger.objects.create(
                employee=request.employee, leave_type=request.leave_type, year=year,
                txn_type='RELEASE_HOLD', days=request.duration_days,
                running_balance=balance.available + request.duration_days,
                reference_request=request,
                notes=f"Hold released for approval - request #{request.id}",
                actor=approver, actor_channel='AGENT',
            )
            LeaveBalanceLedger.objects.create(
                employee=request.employee, leave_type=request.leave_type, year=year,
                txn_type='DEBIT_APPROVED', days=-request.duration_days,
                running_balance=balance.available,
                reference_request=request,
                notes=f"Leave approved - request #{request.id}",
                actor=approver, actor_channel='AGENT',
            )

        # Check if multi-level approval needed
        chain = config.get('approval_chain', [])
        current_step_idx = 0
        for i, step in enumerate(chain):
            if step == 'REPORTING_MANAGER' and approver == request.employee.reporting_manager:
                current_step_idx = i
                break
            elif step == 'HR':
                current_step_idx = i
                break

        if current_step_idx + 1 < len(chain):
            next_step = chain[current_step_idx + 1]
            from .approver_resolver import get_hr_head
            if next_step == 'HR':
                request.current_approver = get_hr_head()
                request.save()
                return request

        request.status = 'APPROVED'
        request.approved_by = approver
        request.approved_at = timezone.now()
        request.approval_remarks = remarks
        request.current_approver = None
        request.save()

        # Check continuous days flag
        flag_threshold = request.leave_type.max_continuous_days_before_flag
        if flag_threshold and request.duration_days > flag_threshold:
            PendingHRAction.objects.create(
                trigger_type='MANAGER_ON_LEAVE',
                employee=request.employee,
                title=f"{request.employee.full_name}: {request.duration_days} continuous {request.leave_type.code} days approved (threshold: {flag_threshold})",
                description=f"Continuous leave exceeds threshold. Review required.",
                priority='MEDIUM',
            )

        # LOP payroll adjustment
        if request.leave_type.code == 'LOP':
            from leaves.models import PayrollAdjustmentPending
            PayrollAdjustmentPending.objects.create(
                employee=request.employee,
                adjustment_type='LOP_DEDUCTION',
                amount_description=f"LOP: {request.duration_days} days from {request.start_date} to {request.end_date}",
                reference_request=request,
            )

        signals.leave_approved.send(
            sender=LeaveRequest,
            employee_id=request.employee.employee_id,
            leave_type=request.leave_type.code,
            start_date=str(request.start_date),
            end_date=str(request.end_date),
            duration=str(request.duration_days),
            approved_by=approver.employee_id,
        )

        return request

    return execute_with_idempotency(
        idempotency_key, 'approve_leave',
        {'approver': approver.employee_id, 'request_id': request_id},
        _do,
    )


@transaction.atomic
def reject_leave(approver, request_id, remarks, idempotency_key=None):
    from .idempotency import execute_with_idempotency

    def _do():
        request = LeaveRequest.objects.select_for_update().get(id=request_id)

        if request.status != 'PENDING':
            raise ValueError(f"Request is not pending (status: {request.status}).")

        if request.current_approver_id != approver.id:
            raise ValueError("You are not the current approver for this request.")

        year = get_leave_year(request.start_date)

        # Release hold
        if request.leave_type.credit_method not in ('ON_DEMAND', 'EVENT'):
            balance = LeaveBalance.objects.get(
                employee=request.employee, leave_type=request.leave_type, year=year
            )
            balance.pending -= request.duration_days
            balance.save()

            LeaveBalanceLedger.objects.create(
                employee=request.employee, leave_type=request.leave_type, year=year,
                txn_type='RELEASE_HOLD', days=request.duration_days,
                running_balance=balance.available,
                reference_request=request,
                notes=f"Hold released - request #{request.id} rejected",
                actor=approver, actor_channel='AGENT',
            )

        request.status = 'REJECTED'
        request.rejected_by = approver
        request.rejected_at = timezone.now()
        request.rejection_remarks = remarks
        request.current_approver = None
        request.save()

        signals.leave_rejected.send(
            sender=LeaveRequest,
            employee_id=request.employee.employee_id,
            leave_type=request.leave_type.code,
            request_id=request.id,
            rejected_by=approver.employee_id,
            remarks=remarks,
        )

        return request

    return execute_with_idempotency(
        idempotency_key, 'reject_leave',
        {'approver': approver.employee_id, 'request_id': request_id},
        _do,
    )
