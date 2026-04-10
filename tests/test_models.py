from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.db import IntegrityError
from .test_helpers import *


class TestModels(TestCase):
    def setUp(self):
        self.dept = create_test_department()
        self.desg = create_test_designation()
        self.emp = create_test_employee(department=self.dept, designation=self.desg)

    def test_employee_full_name(self):
        self.assertEqual(self.emp.full_name, 'Test User')

    def test_employee_service_days(self):
        self.assertGreater(self.emp.service_days, 0)

    def test_employee_is_on_probation(self):
        self.assertFalse(self.emp.is_on_probation)
        self.emp.probation_status = 'ON_PROBATION'
        self.assertTrue(self.emp.is_on_probation)

    def test_leave_type_creation(self):
        lt = create_test_leave_type()
        self.assertEqual(lt.code, 'SL')
        self.assertEqual(lt.entitlement_days, 8)

    def test_leave_balance_available(self):
        lt = create_test_leave_type()
        bal = create_test_balance(self.emp, lt, entitled=Decimal('8.0'))
        self.assertEqual(bal.available, Decimal('8.0'))

        bal.used = Decimal('2.0')
        bal.pending = Decimal('1.0')
        bal.save()
        self.assertEqual(bal.available, Decimal('5.0'))

    def test_leave_balance_unique_together(self):
        lt = create_test_leave_type()
        create_test_balance(self.emp, lt)
        with self.assertRaises(IntegrityError):
            create_test_balance(self.emp, lt)

    def test_department_str(self):
        self.assertEqual(str(self.dept), 'Engineering')

    def test_leave_balance_with_carry_and_adjusted(self):
        lt = create_test_leave_type()
        bal = create_test_balance(self.emp, lt, entitled=Decimal('8.0'))
        bal.carried_forward = Decimal('3.0')
        bal.adjusted = Decimal('2.0')
        bal.used = Decimal('1.0')
        bal.save()
        self.assertEqual(bal.available, Decimal('12.0'))
        self.assertEqual(bal.total_credited, Decimal('13.0'))
