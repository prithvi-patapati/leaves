from django.core.management.base import BaseCommand
from leaves.models import CompanyConfig


class Command(BaseCommand):
    help = 'Seed company config'

    def handle(self, *args, **options):
        config, created = CompanyConfig.objects.get_or_create(
            pk=1,
            defaults={
                'leave_year_start_month': 4,
                'leave_year_start_day': 1,
                'working_days_per_week': 5,
                'weekend_days': [5, 6],
                'max_optional_holidays_per_year': 3,
                'top_level_approval_mode': 'SELF_APPROVE_WITH_HR_NOTIFY',
            }
        )
        status = 'Created' if created else 'Already exists'
        self.stdout.write(self.style.SUCCESS(f'{status}: Company config.'))
