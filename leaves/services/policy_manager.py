from django.db import transaction
from django.forms.models import model_to_dict
from leaves.models import LeaveType, LeavePolicyVersion
from leaves import signals


@transaction.atomic
def create_leave_type(actor, config_dict, via='API', idempotency_key=None):
    from .idempotency import execute_with_idempotency

    def _do():
        lt = LeaveType.objects.create(**config_dict)
        LeavePolicyVersion.objects.create(
            leave_type=lt, version=1,
            snapshot=_serialize_leave_type(lt),
            change_summary=f"Initial creation of {lt.code} - {lt.name}",
            changed_by=actor, changed_via=via,
        )
        return lt

    return execute_with_idempotency(
        idempotency_key, 'create_leave_type', config_dict, _do
    )


@transaction.atomic
def update_leave_type(actor, code, changes, change_summary, effective_mode='PROSPECTIVE',
                      via='API', idempotency_key=None):
    from .idempotency import execute_with_idempotency

    def _do():
        lt = LeaveType.objects.select_for_update().get(code=code)
        for field, value in changes.items():
            setattr(lt, field, value)
        lt.save()

        latest_version = LeavePolicyVersion.objects.filter(leave_type=lt).count()
        LeavePolicyVersion.objects.create(
            leave_type=lt, version=latest_version + 1,
            snapshot=_serialize_leave_type(lt),
            change_summary=change_summary,
            effective_mode=effective_mode,
            changed_by=actor, changed_via=via,
        )

        signals.policy_changed.send(
            sender=LeaveType,
            code=lt.code,
            change_summary=change_summary,
            changed_by=actor.employee_id if actor else None,
            version=latest_version + 1,
            effective_mode=effective_mode,
        )
        return lt

    return execute_with_idempotency(
        idempotency_key, 'update_leave_type',
        {'code': code, 'changes': str(changes)}, _do,
    )


@transaction.atomic
def deactivate_leave_type(actor, code, idempotency_key=None):
    from .idempotency import execute_with_idempotency

    def _do():
        lt = LeaveType.objects.get(code=code)
        lt.is_active = False
        lt.save()

        latest_version = LeavePolicyVersion.objects.filter(leave_type=lt).count()
        LeavePolicyVersion.objects.create(
            leave_type=lt, version=latest_version + 1,
            snapshot=_serialize_leave_type(lt),
            change_summary=f"Deactivated {lt.code}",
            changed_by=actor, changed_via='API',
        )
        return lt

    return execute_with_idempotency(
        idempotency_key, 'deactivate_leave_type', {'code': code}, _do,
    )


def get_all_policies():
    from leaves.models import LeaveType
    return LeaveType.objects.filter(is_active=True)


def _serialize_leave_type(lt):
    return {
        'code': lt.code, 'name': lt.name, 'entitlement_days': str(lt.entitlement_days),
        'credit_method': lt.credit_method, 'half_day_allowed': lt.half_day_allowed,
        'advance_notice_days': lt.advance_notice_days, 'probation_eligible': lt.probation_eligible,
        'approval_chain': lt.approval_chain, 'is_active': lt.is_active,
        'year_end_action': lt.year_end_action, 'carry_forward_max': lt.carry_forward_max,
    }
