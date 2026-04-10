from datetime import date
from decimal import Decimal
from employees.models import Department, Designation, Employee
from leaves.models import LeaveType, LeaveBalance, CompanyConfig


def create_test_department(code='ENGINEERING', name='Engineering'):
    return Department.objects.create(code=code, name=name)


def create_test_designation(title='Software Engineer', level=3):
    return Designation.objects.create(title=title, level=level)


def create_test_employee(employee_id='TEST-001', first_name='Test', last_name='User',
                         department=None, designation=None, **kwargs):
    dept = department or create_test_department()
    desg = designation or create_test_designation()
    defaults = {
        'email': f'{employee_id.lower()}@test.co',
        'gender': 'M',
        'date_of_joining': date(2024, 1, 1),
        'employment_type': 'FULL_TIME',
        'probation_status': 'CONFIRMED',
    }
    defaults.update(kwargs)
    return Employee.objects.create(
        employee_id=employee_id, first_name=first_name, last_name=last_name,
        department=dept, designation=desg, **defaults,
    )


def create_test_leave_type(code='SL', name='Sick Leave', **kwargs):
    defaults = {
        'entitlement_days': 8, 'credit_method': 'BULK',
        'approval_chain': ['REPORTING_MANAGER'], 'is_pro_rata': True,
        'half_day_allowed': True, 'probation_eligible': True,
        'can_apply_retroactively': True,
    }
    defaults.update(kwargs)
    return LeaveType.objects.create(code=code, name=name, **defaults)


def create_test_balance(employee, leave_type, year=2026, entitled=Decimal('8.0')):
    return LeaveBalance.objects.create(
        employee=employee, leave_type=leave_type, year=year, entitled=entitled,
    )


def setup_company_config():
    CompanyConfig.objects.get_or_create(pk=1, defaults={
        'leave_year_start_month': 4,
        'weekend_days': [5, 6],
        'working_days_per_week': 5,
    })
