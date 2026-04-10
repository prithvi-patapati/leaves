from datetime import date
from django.test import TestCase
from employees.models import Employee, EmployeeChangeLog, PendingHRAction
from employees.services.employee_service import (
    add_employee, update_employee, confirm_employee, deactivate_employee,
)
from .test_helpers import create_test_department, create_test_designation


class TestEmployeeService(TestCase):
    def setUp(self):
        self.dept = create_test_department()
        self.desg = create_test_designation()

    def test_add_employee(self):
        emp, summary = add_employee(
            employee_id='NEW-001', first_name='New', last_name='User',
            email='new@test.co', gender='M', department=self.dept,
            designation=self.desg, date_of_joining=date(2026, 4, 1),
        )
        self.assertEqual(emp.employee_id, 'NEW-001')
        self.assertTrue(PendingHRAction.objects.filter(
            employee=emp, trigger_type='NEW_JOINER'
        ).exists())

    def test_confirm_employee(self):
        emp, _ = add_employee(
            employee_id='CONF-001', first_name='Conf', email='conf@test.co',
            gender='M', department=self.dept, designation=self.desg,
            date_of_joining=date(2024, 1, 1), probation_status='ON_PROBATION',
        )
        confirmed = confirm_employee(None, 'CONF-001')
        self.assertEqual(confirmed.probation_status, 'CONFIRMED')
        self.assertEqual(confirmed.confirmation_date, date.today())

    def test_deactivate_employee(self):
        emp, _ = add_employee(
            employee_id='EXIT-001', first_name='Exit', email='exit@test.co',
            gender='M', department=self.dept, designation=self.desg,
            date_of_joining=date(2024, 1, 1),
        )
        deactivated = deactivate_employee(None, 'EXIT-001', date.today(), 'RESIGNED')
        self.assertFalse(deactivated.is_active)
        self.assertTrue(PendingHRAction.objects.filter(
            employee=deactivated, trigger_type='EXIT'
        ).exists())

    def test_update_creates_changelog(self):
        emp, _ = add_employee(
            employee_id='UPD-001', first_name='Upd', email='upd@test.co',
            gender='M', department=self.dept, designation=self.desg,
            date_of_joining=date(2024, 1, 1),
        )
        update_employee(None, 'UPD-001', phone='1234567890')
        self.assertTrue(EmployeeChangeLog.objects.filter(
            employee=emp, field_changed='phone'
        ).exists())
