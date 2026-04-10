from django.core.management.base import BaseCommand
from employees.models import OnboardingTemplate


class Command(BaseCommand):
    help = 'Seed onboarding templates'

    def handle(self, *args, **options):
        template, created = OnboardingTemplate.objects.get_or_create(
            name='Default New Joiner',
            defaults={
                'priority': 10,
                'actions': [{'type': 'CREDIT_LEAVES'}],
                'is_active': True,
            }
        )
        status = 'Created' if created else 'Exists'
        self.stdout.write(self.style.SUCCESS(f'{status}: {template.name}'))
