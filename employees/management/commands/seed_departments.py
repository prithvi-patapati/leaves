from django.core.management.base import BaseCommand
from employees.models import Department


DEPARTMENTS = [
    ('Engineering', 'ENGINEERING'),
    ('Program Management', 'PROGRAM_MGMT'),
    ('Admin', 'ADMIN'),
    ('Human Resources', 'HR'),
    ('Marketing', 'MARKETING'),
    ('Operations', 'OPERATIONS'),
]


class Command(BaseCommand):
    help = 'Seed departments'

    def handle(self, *args, **options):
        for name, code in DEPARTMENTS:
            dept, created = Department.objects.get_or_create(
                code=code, defaults={'name': name}
            )
            status = 'Created' if created else 'Exists'
            self.stdout.write(f'{status}: {dept.name} ({dept.code})')
        self.stdout.write(self.style.SUCCESS(f'Done. {Department.objects.count()} departments.'))
