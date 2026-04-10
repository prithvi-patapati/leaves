from django.core.management.base import BaseCommand
from employees.models import Designation


DESIGNATIONS = [
    ('CEO', 9),
    ('CTO', 8),
    ('Senior Project Manager', 6),
    ('Senior Program Manager', 6),
    ('Senior HR Manager', 6),
    ('Senior Software Engineer', 4),
    ('Senior Software Developer', 4),
    ('Software Engineer', 3),
    ('Software Developer', 3),
    ('Data Analyst', 3),
    ('UI/UX Designer', 3),
    ('Program Manager', 5),
    ('Talent Acquisition Specialist', 3),
    ('Admin', 2),
    ('Intern', 0),
    ('Software Developer Intern', 0),
]


class Command(BaseCommand):
    help = 'Seed designations'

    def handle(self, *args, **options):
        for title, level in DESIGNATIONS:
            desg, created = Designation.objects.get_or_create(
                title=title, defaults={'level': level}
            )
            status = 'Created' if created else 'Exists'
            self.stdout.write(f'{status}: {desg.title} (level {desg.level})')
        self.stdout.write(self.style.SUCCESS(f'Done. {Designation.objects.count()} designations.'))
