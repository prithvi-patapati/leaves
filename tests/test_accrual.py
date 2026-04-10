from datetime import date
from decimal import Decimal
from django.test import TestCase
from leaves.models import EmployeeOverride, LeaveBalance, LeaveBalanceLedger
from leaves.services.accrual import run_monthly_accrual, run_bulk_credit
from .test_helpers import *


class TestAccrual(TestCase):
    def setUp(self):
        setup_company_config()
        self.dept = create_test_department()
        self.desg = create_test_designation()
        self.emp = create_test_employee(department=self.dept, designation=self.desg)
        self.pl = create_test_leave_type(
            code='PL', name='Planned Leave',
            credit_method='MONTHLY', monthly_accrual_rate=Decimal('0.5'),
            entitlement_days=Decimal('6'),
        )

    def test_monthly_accrual(self):
        LeaveBalance.objects.create(employee=self.emp, leave_type=self.pl, year=2026)
        results = run_monthly_accrual(date(2026, 4, 1))
        self.assertEqual(len(results), 1)
        bal = LeaveBalance.objects.get(employee=self.emp, leave_type=self.pl, year=2026)
        self.assertEqual(bal.entitled, Decimal('0.5'))

    def test_accrual_idempotent(self):
        LeaveBalance.objects.create(employee=self.emp, leave_type=self.pl, year=2026)
        run_monthly_accrual(date(2026, 4, 1))
        run_monthly_accrual(date(2026, 4, 1))
        entries = LeaveBalanceLedger.objects.filter(
            employee=self.emp, txn_type='CREDIT_ACCRUAL'
        )
        self.assertEqual(entries.count(), 1)

    def test_accrual_blocked_by_override(self):
        LeaveBalance.objects.create(employee=self.emp, leave_type=self.pl, year=2026)
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.pl,
            block_accrual=True, effective_from=date(2026, 1, 1),
            reason='Test', created_via='API',
        )
        results = run_monthly_accrual(date(2026, 4, 1))
        self.assertEqual(len(results), 0)

    def test_bulk_credit(self):
        sl = create_test_leave_type()
        results = run_bulk_credit(2026)
        self.assertEqual(len(results), 1)
        bal = LeaveBalance.objects.get(employee=self.emp, leave_type=sl, year=2026)
        self.assertEqual(bal.entitled, Decimal('8.0'))
