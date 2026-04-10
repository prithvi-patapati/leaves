import os
import openpyxl
from django.core.management.base import BaseCommand
from employees.models import Employee, Department, Designation


DEPT_MAP = {
    'Engineering': 'ENGINEERING',
    'Program Management': 'PROGRAM_MGMT',
    'Admin': 'ADMIN',
    'Human Resources': 'HR',
    'Marketing': 'MARKETING',
    'Operations': 'OPERATIONS',
    'Not available': 'ENGINEERING',
}

FEMALE_NAMES = {
    'meena', 'gayathri', 'chandrakala', 'hasini', 'bhavishya', 'sneha',
    'kavya', 'deepa', 'priya', 'ananya', 'divya', 'swathi', 'lakshmi',
    'pooja', 'neha', 'keerthana', 'sravya', 'mounika', 'vaishnavi',
    'anusha', 'harshitha', 'varsha', 'shravani', 'rishitha',
}


class Command(BaseCommand):
    help = 'Import employees from xlsx'

    def handle(self, *args, **options):
        xlsx_path = os.path.join('data', 'employee-directory-sorted-by-id.xlsx')
        wb = openpyxl.load_workbook(xlsx_path)
        ws = wb.active

        rows = []
        manager_map = {}  # name -> employee_id

        # First pass: create employees
        for row in ws.iter_rows(min_row=2, values_only=True):
            name, emp_id, email, dept_name, role, manager_name = row
            if not emp_id:
                continue

            emp_id = str(emp_id).strip().replace(' ', '')
            name = str(name).strip().replace('.', ' ')
            email = str(email).strip() if email else ''
            dept_name = str(dept_name).strip() if dept_name else 'Engineering'
            role = str(role).strip() if role else 'Software Engineer'
            manager_name = str(manager_name).strip() if manager_name else 'Not available'

            parts = name.split()
            first_name = parts[0] if parts else name
            last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''

            dept_code = DEPT_MAP.get(dept_name, 'ENGINEERING')
            dept = Department.objects.get(code=dept_code)
            desg = Designation.objects.get(title=role)

            # Guess gender from first name
            gender = 'F' if first_name.lower() in FEMALE_NAMES else 'M'

            # Employment type
            employment_type = 'INTERN' if emp_id.startswith('INT') else 'FULL_TIME'

            emp, created = Employee.objects.get_or_create(
                employee_id=emp_id,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email or f'{emp_id.lower()}@gamyam.co',
                    'gender': gender,
                    'department': dept,
                    'designation': desg,
                    'employment_type': employment_type,
                    'date_of_joining': '2024-01-01',
                    'probation_status': 'CONFIRMED',
                    'is_active': True,
                }
            )

            manager_map[name] = emp_id
            rows.append((emp_id, manager_name))

            status = 'Created' if created else 'Exists'
            self.stdout.write(f'{status}: {emp.employee_id} - {emp.full_name}')

        # Second pass: set reporting managers
        updated = 0
        for emp_id, manager_name in rows:
            if manager_name == 'Not available' or not manager_name:
                continue

            manager_emp_id = manager_map.get(manager_name)
            if manager_emp_id:
                try:
                    emp = Employee.objects.get(employee_id=emp_id)
                    manager = Employee.objects.get(employee_id=manager_emp_id)
                    emp.reporting_manager = manager
                    emp.save()
                    updated += 1
                except Employee.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'Could not set manager for {emp_id}: {manager_name}'))

        self.stdout.write(self.style.SUCCESS(
            f'Done. {Employee.objects.count()} employees. {updated} manager relationships set.'
        ))
