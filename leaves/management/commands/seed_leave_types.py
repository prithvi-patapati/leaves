from django.core.management.base import BaseCommand
from leaves.models import LeaveType, LeavePolicyVersion


LEAVE_TYPES = [
    {
        'code': 'SL', 'name': 'Sick Leave', 'entitlement_days': 8,
        'credit_method': 'BULK', 'is_pro_rata': True,
        'year_end_action': 'LAPSE', 'half_day_allowed': True,
        'advance_notice_days': 0, 'can_apply_in_advance': False,
        'can_apply_retroactively': True, 'document_required': True,
        'document_required_after_days': 2, 'probation_eligible': True,
        'max_continuous_days_before_flag': 5,
        'approval_chain': ['REPORTING_MANAGER'],
    },
    {
        'code': 'PL', 'name': 'Planned / Casual Leave', 'entitlement_days': 6,
        'credit_method': 'MONTHLY', 'monthly_accrual_rate': 0.5, 'is_pro_rata': True,
        'year_end_action': 'CONVERT', 'half_day_allowed': True,
        'advance_notice_days': 2, 'can_apply_in_advance': True,
        'can_apply_retroactively': False, 'probation_eligible': True,
        'approval_chain': ['REPORTING_MANAGER'],
    },
    {
        'code': 'EL', 'name': 'Earned Leave', 'entitlement_days': 6,
        'credit_method': 'MONTHLY', 'monthly_accrual_rate': 0.5, 'is_pro_rata': True,
        'year_end_action': 'CARRY', 'carry_forward_max': 30,
        'half_day_allowed': False, 'advance_notice_days': 3,
        'can_apply_in_advance': True, 'probation_eligible': True,
        'approval_chain': ['REPORTING_MANAGER'],
    },
    {
        'code': 'LOP', 'name': 'Loss of Pay', 'entitlement_days': 0,
        'credit_method': 'ON_DEMAND', 'year_end_action': 'LAPSE',
        'half_day_allowed': True, 'advance_notice_days': 0,
        'probation_eligible': True, 'max_continuous_days_before_flag': 30,
        'approval_chain': ['REPORTING_MANAGER', 'HR'],
    },
    {
        'code': 'WFH', 'name': 'Work From Home', 'entitlement_days': 6,
        'credit_method': 'BULK', 'is_pro_rata': True,
        'year_end_action': 'LAPSE', 'half_day_allowed': True,
        'advance_notice_days': 1, 'can_apply_in_advance': True,
        'probation_eligible': False, 'consecutive_day_restriction': True,
        'approval_chain': ['REPORTING_MANAGER'],
    },
    {
        'code': 'BL', 'name': 'Bereavement Leave', 'entitlement_days': 5,
        'credit_method': 'EVENT', 'year_end_action': 'LAPSE',
        'half_day_allowed': False, 'document_required': True,
        'document_required_after_days': 0, 'probation_eligible': True,
        'approval_chain': ['REPORTING_MANAGER'],
    },
    {
        'code': 'ML', 'name': 'Maternity Leave', 'entitlement_days': 130,
        'credit_method': 'EVENT', 'year_end_action': 'LAPSE',
        'half_day_allowed': False, 'gender_restriction': 'F',
        'min_service_days': 80, 'document_required': True,
        'probation_eligible': True,
        'approval_chain': ['REPORTING_MANAGER', 'HR'],
    },
    {
        'code': 'PtL', 'name': 'Paternity Leave', 'entitlement_days': 21,
        'credit_method': 'EVENT', 'year_end_action': 'LAPSE',
        'half_day_allowed': False, 'gender_restriction': 'M',
        'avail_window_days': 90, 'document_required': True,
        'probation_eligible': False,
        'approval_chain': ['REPORTING_MANAGER'],
    },
    {
        'code': 'OH', 'name': 'Optional Holiday', 'entitlement_days': 3,
        'credit_method': 'EVENT', 'year_end_action': 'LAPSE',
        'half_day_allowed': False, 'probation_eligible': True,
        'approval_chain': ['REPORTING_MANAGER'],
    },
]


class Command(BaseCommand):
    help = 'Seed leave types'

    def handle(self, *args, **options):
        for lt_data in LEAVE_TYPES:
            code = lt_data['code']
            lt, created = LeaveType.objects.get_or_create(
                code=code, defaults=lt_data,
            )
            if created:
                # Set PL.convert_to = EL
                if code == 'PL':
                    el = LeaveType.objects.filter(code='EL').first()
                    if el:
                        lt.convert_to = el
                        lt.save()

                LeavePolicyVersion.objects.create(
                    leave_type=lt, version=1,
                    snapshot={
                        'code': lt.code, 'name': lt.name,
                        'entitlement_days': str(lt.entitlement_days),
                        'credit_method': lt.credit_method,
                    },
                    change_summary=f'Initial creation of {lt.code} - {lt.name}',
                    changed_via='ADMIN',
                )
                self.stdout.write(f'Created: {lt}')
            else:
                self.stdout.write(f'Exists: {lt}')

        self.stdout.write(self.style.SUCCESS(f'Done. {LeaveType.objects.count()} leave types.'))
