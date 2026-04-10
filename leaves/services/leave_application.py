from datetime import date
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from leaves.models import LeaveType, LeaveRequest, LeaveBalance, LeaveBalanceLedger, LeavePolicyVersion
from leaves.validators import run_validators
from leaves import signals
from .config_resolver import get_effective_config
from .approver_resolver import determine_approver
from .duration_calculator import calculate_leave_days, get_leave_year
from .idempotency import execute_with_idempotency


@transaction.atomic
def apply_leave(employee, leave_type_code, start_date, end_date, reason,
                is_half_day=False, half_day_period=None, event_date=None,
                idempotency_key=None, via='AGENT'):

    def _do():
        leave_type = LeaveType.objects.get(code=leave_type_code)
        config = get_effective_config(employee, leave_type, start_date)
        duration = calculate_leave_days(start_date, end_date, is_half_day, employee)

        request_data = {
            'start_date': start_date,
            'end_date': end_date,
            'duration': duration,
            'is_half_day': is_half_day,
            'half_day_period': half_day_period,
            'event_date': event_date,
            'reason': reason,
            'document': None,
        }

        passed, error = run_validators(employee, leave_type, request_data, config)
        if not passed:
            raise ValueError(error)

        # Get or create policy version snapshot
        policy_version = LeavePolicyVersion.objects.filter(
            leave_type=leave_type
        ).order_by('-version').first()

        approver = determine_approver(employee, leave_type, config)

        request = LeaveRequest.objects.create(
            employee=employee,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            duration_days=duration,
            is_half_day=is_half_day,
            half_day_period=half_day_period,
            reason=reason,
            status='PENDING',
            current_approver=approver,
            policy_version=policy_version,
            applied_via=via,
            idempotency_key=idempotency_key,
        )

        # Hold balance
        if leave_type.credit_method not in ('ON_DEMAND', 'EVENT'):
            year = get_leave_year(start_date)
            balance = LeaveBalance.objects.get(
                employee=employee, leave_type=leave_type, year=year
            )
            balance.pending += duration
            balance.save()

            LeaveBalanceLedger.objects.create(
                employee=employee, leave_type=leave_type, year=year,
                txn_type='HOLD_PENDING', days=-duration,
                running_balance=balance.available,
                reference_request=request,
                notes=f"Hold for leave request #{request.id}",
                actor=employee, actor_channel=via,
            )

        signals.leave_applied.send(
            sender=LeaveRequest,
            employee_id=employee.employee_id,
            leave_type=leave_type_code,
            start_date=str(start_date),
            end_date=str(end_date),
            duration=str(duration),
        )

        return request

    return execute_with_idempotency(
        idempotency_key, 'apply_leave',
        {'employee': employee.employee_id, 'leave_type': leave_type_code,
         'start_date': str(start_date), 'end_date': str(end_date)},
        _do,
    )


@transaction.atomic
def cancel_leave(employee, request_id, reason=None, idempotency_key=None):
    def _do():
        request = LeaveRequest.objects.select_for_update().get(id=request_id)
        if request.employee_id != employee.id:
            raise ValueError("You can only cancel your own leave requests.")

        if request.status not in ('PENDING', 'APPROVED'):
            raise ValueError(f"Cannot cancel a {request.status} request.")

        year = get_leave_year(request.start_date)

        if request.status == 'PENDING':
            # Release hold
            if request.leave_type.credit_method not in ('ON_DEMAND', 'EVENT'):
                balance = LeaveBalance.objects.get(
                    employee=employee, leave_type=request.leave_type, year=year
                )
                balance.pending -= request.duration_days
                balance.save()

                LeaveBalanceLedger.objects.create(
                    employee=employee, leave_type=request.leave_type, year=year,
                    txn_type='RELEASE_HOLD', days=request.duration_days,
                    running_balance=balance.available,
                    reference_request=request,
                    notes=f"Hold released - request #{request.id} cancelled",
                    actor=employee, actor_channel='AGENT',
                )

        elif request.status == 'APPROVED':
            if request.leave_type.credit_method not in ('ON_DEMAND', 'EVENT'):
                balance = LeaveBalance.objects.get(
                    employee=employee, leave_type=request.leave_type, year=year
                )
                balance.used -= request.duration_days
                balance.save()

                LeaveBalanceLedger.objects.create(
                    employee=employee, leave_type=request.leave_type, year=year,
                    txn_type='CREDIT_REVERSAL', days=request.duration_days,
                    running_balance=balance.available,
                    reference_request=request,
                    notes=f"Reversal - approved request #{request.id} cancelled",
                    actor=employee, actor_channel='AGENT',
                )

        request.status = 'CANCELLED'
        request.save()

        signals.leave_cancelled.send(
            sender=LeaveRequest,
            employee_id=employee.employee_id,
            leave_type=request.leave_type.code,
            start_date=str(request.start_date),
            end_date=str(request.end_date),
            was_approved=request.status == 'APPROVED',
        )

        return request

    return execute_with_idempotency(
        idempotency_key, 'cancel_leave',
        {'employee': employee.employee_id, 'request_id': request_id},
        _do,
    )


def validate_leave(employee, leave_type_code, start_date, end_date,
                   is_half_day=False, half_day_period=None):
    leave_type = LeaveType.objects.get(code=leave_type_code)
    config = get_effective_config(employee, leave_type, start_date)
    duration = calculate_leave_days(start_date, end_date, is_half_day, employee)

    request_data = {
        'start_date': start_date,
        'end_date': end_date,
        'duration': duration,
        'is_half_day': is_half_day,
        'half_day_period': half_day_period,
        'event_date': None,
        'reason': 'validation check',
        'document': None,
    }

    return run_validators(employee, leave_type, request_data, config)


def get_my_requests(employee_id, status=None):
    from employees.models import Employee
    employee = Employee.objects.get(employee_id=employee_id)
    qs = LeaveRequest.objects.filter(employee=employee).select_related('leave_type', 'current_approver')
    if status:
        qs = qs.filter(status=status)
    return qs.order_by('-applied_at')


def get_team_requests(actor, status=None):
    from employees.models import Employee
    reports = Employee.objects.filter(reporting_manager=actor, is_active=True)
    qs = LeaveRequest.objects.filter(employee__in=reports).select_related('employee', 'leave_type')
    if status:
        qs = qs.filter(status=status)
    return qs.order_by('-applied_at')


def get_all_requests(status=None, employee_id=None):
    qs = LeaveRequest.objects.all().select_related('employee', 'leave_type')
    if status:
        qs = qs.filter(status=status)
    if employee_id:
        qs = qs.filter(employee__employee_id=employee_id)
    return qs.order_by('-applied_at')
