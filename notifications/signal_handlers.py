"""
Connect to existing Django signals from leaves and employees apps.
Creates Activity records for every significant event.

To disconnect: just remove 'notifications' from INSTALLED_APPS.
"""
from django.dispatch import receiver
from .models import Activity


def _log(event_type, title, actor_id='', actor_name='', target_id='', target_name='',
         visibility='EMPLOYEE', manager_id='', metadata=None):
    Activity.objects.create(
        event_type=event_type,
        title=title,
        actor_id=actor_id,
        actor_name=actor_name,
        target_id=target_id,
        target_name=target_name,
        visibility=visibility,
        manager_id=manager_id,
        metadata=metadata or {},
        channels=['web'],
    )


# ── Leave Signals ──

try:
    from leaves.signals import (
        leave_applied, leave_approved, leave_rejected,
        leave_cancelled, policy_changed, balance_adjusted,
    )

    @receiver(leave_applied)
    def on_leave_applied(sender, **kwargs):
        _log(
            event_type='LEAVE_APPLIED',
            title=f"{kwargs.get('employee_name', '')} applied for {kwargs.get('leave_type', '')} ({kwargs.get('start_date', '')} to {kwargs.get('end_date', '')})",
            target_id=kwargs.get('employee_id', ''),
            target_name=kwargs.get('employee_name', ''),
            manager_id=kwargs.get('approver_id', ''),
            visibility='EMPLOYEE',
            metadata={
                'leave_type': kwargs.get('leave_type', ''),
                'start_date': str(kwargs.get('start_date', '')),
                'end_date': str(kwargs.get('end_date', '')),
                'duration': str(kwargs.get('duration', '')),
                'reason': kwargs.get('reason', ''),
            },
        )

    @receiver(leave_approved)
    def on_leave_approved(sender, **kwargs):
        _log(
            event_type='LEAVE_APPROVED',
            title=f"{kwargs.get('employee_name', '')}'s {kwargs.get('leave_type', '')} approved by {kwargs.get('approved_by_name', '')}",
            actor_id=kwargs.get('approved_by_id', ''),
            actor_name=kwargs.get('approved_by_name', ''),
            target_id=kwargs.get('employee_id', ''),
            target_name=kwargs.get('employee_name', ''),
            manager_id=kwargs.get('approved_by_id', ''),
            visibility='EMPLOYEE',
            metadata={
                'leave_type': kwargs.get('leave_type', ''),
                'start_date': str(kwargs.get('start_date', '')),
                'end_date': str(kwargs.get('end_date', '')),
            },
        )

    @receiver(leave_rejected)
    def on_leave_rejected(sender, **kwargs):
        _log(
            event_type='LEAVE_REJECTED',
            title=f"{kwargs.get('employee_name', '')}'s {kwargs.get('leave_type', '')} rejected by {kwargs.get('rejected_by_name', '')}",
            actor_id=kwargs.get('rejected_by_id', ''),
            actor_name=kwargs.get('rejected_by_name', ''),
            target_id=kwargs.get('employee_id', ''),
            target_name=kwargs.get('employee_name', ''),
            manager_id=kwargs.get('rejected_by_id', ''),
            visibility='EMPLOYEE',
            metadata={
                'leave_type': kwargs.get('leave_type', ''),
                'remarks': kwargs.get('remarks', ''),
            },
        )

    @receiver(leave_cancelled)
    def on_leave_cancelled(sender, **kwargs):
        _log(
            event_type='LEAVE_CANCELLED',
            title=f"{kwargs.get('employee_name', '')} cancelled their {kwargs.get('leave_type', '')}",
            target_id=kwargs.get('employee_id', ''),
            target_name=kwargs.get('employee_name', ''),
            visibility='EMPLOYEE',
            metadata={
                'leave_type': kwargs.get('leave_type', ''),
                'was_approved': kwargs.get('was_approved', False),
            },
        )

    @receiver(policy_changed)
    def on_policy_changed(sender, **kwargs):
        _log(
            event_type='POLICY_CHANGED',
            title=f"Leave policy updated: {kwargs.get('change_summary', '')}",
            actor_id=kwargs.get('changed_by_id', ''),
            actor_name=kwargs.get('changed_by_name', ''),
            visibility='HR',
            metadata={
                'leave_type': kwargs.get('leave_type_code', ''),
                'version': kwargs.get('version', ''),
                'effective_mode': kwargs.get('effective_mode', ''),
            },
        )

    @receiver(balance_adjusted)
    def on_balance_adjusted(sender, **kwargs):
        _log(
            event_type='BALANCE_ADJUSTED',
            title=f"{kwargs.get('employee_name', '')}'s {kwargs.get('leave_type', '')} adjusted by {kwargs.get('days', '')} days",
            actor_id=kwargs.get('adjusted_by_id', ''),
            actor_name=kwargs.get('adjusted_by_name', ''),
            target_id=kwargs.get('employee_id', ''),
            target_name=kwargs.get('employee_name', ''),
            visibility='HR',
            metadata={
                'leave_type': kwargs.get('leave_type', ''),
                'days': str(kwargs.get('days', '')),
                'reason': kwargs.get('reason', ''),
            },
        )

except ImportError:
    pass  # leaves app not installed


# ── Employee Signals ──

try:
    from employees.signals import (
        employee_created, employee_confirmed,
        employee_deactivated, employee_transferred,
    )

    @receiver(employee_created)
    def on_employee_created(sender, **kwargs):
        _log(
            event_type='EMPLOYEE_ADDED',
            title=f"New employee added: {kwargs.get('employee_id', '')}",
            target_id=kwargs.get('employee_id', ''),
            visibility='HR',
            metadata={
                'department': kwargs.get('department', ''),
                'designation': kwargs.get('designation', ''),
            },
        )

    @receiver(employee_confirmed)
    def on_employee_confirmed(sender, **kwargs):
        _log(
            event_type='EMPLOYEE_CONFIRMED',
            title=f"{kwargs.get('employee_id', '')} probation confirmed",
            target_id=kwargs.get('employee_id', ''),
            visibility='HR',
        )

    @receiver(employee_deactivated)
    def on_employee_deactivated(sender, **kwargs):
        _log(
            event_type='EMPLOYEE_DEACTIVATED',
            title=f"{kwargs.get('employee_id', '')} deactivated ({kwargs.get('exit_reason', '')})",
            target_id=kwargs.get('employee_id', ''),
            visibility='HR',
            metadata={'exit_reason': kwargs.get('exit_reason', '')},
        )

    @receiver(employee_transferred)
    def on_employee_transferred(sender, **kwargs):
        _log(
            event_type='EMPLOYEE_TRANSFERRED',
            title=f"{kwargs.get('employee_id', '')} transferred from {kwargs.get('old_department', '')} to {kwargs.get('new_department', '')}",
            target_id=kwargs.get('employee_id', ''),
            visibility='HR',
            metadata={
                'old_department': kwargs.get('old_department', ''),
                'new_department': kwargs.get('new_department', ''),
            },
        )

except ImportError:
    pass  # employees app not installed
