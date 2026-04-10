from django.utils import timezone
from employees.models import PendingHRAction


def get_pending(status='OPEN', priority=None):
    qs = PendingHRAction.objects.filter(status=status)
    if priority:
        qs = qs.filter(priority=priority)
    return qs.select_related('employee')


def resolve_action(actor, action_id, status='RESOLVED', notes=''):
    action = PendingHRAction.objects.get(id=action_id)
    action.status = status
    action.resolved_by = actor
    action.resolved_at = timezone.now()
    action.resolution_notes = notes
    action.save()
    return action


def execute_suggested_action(actor, action_id, suggestion_index):
    action = PendingHRAction.objects.get(id=action_id)
    if suggestion_index >= len(action.suggested_actions):
        raise ValueError("Invalid suggestion index.")

    suggestion = action.suggested_actions[suggestion_index]
    action_type = suggestion.get('action')

    if action_type == 'remove_override':
        from .override_manager import remove_override
        remove_override(actor, suggestion['override_id'], suggestion.get('reason', ''))
    elif action_type == 'reroute_request':
        from leaves.models import LeaveRequest
        from employees.models import Employee
        request = LeaveRequest.objects.get(id=suggestion['request_id'])
        new_approver = Employee.objects.get(employee_id=suggestion['new_approver'])
        request.current_approver = new_approver
        request.save()

    return action


def create_nudge(trigger_type, employee, title, description,
                 affected_overrides=None, affected_requests=None,
                 suggested_actions=None, priority='MEDIUM'):
    return PendingHRAction.objects.create(
        trigger_type=trigger_type,
        employee=employee,
        title=title,
        description=description,
        affected_overrides=affected_overrides or [],
        affected_requests=affected_requests or [],
        suggested_actions=suggested_actions or [],
        priority=priority,
    )
