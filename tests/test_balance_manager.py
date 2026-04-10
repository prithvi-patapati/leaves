from decimal import Decimal
from django.test import TestCase
from leaves.models import LeaveBalance, LeaveBalanceLedger
from leaves.services.balance_manager import credit_balance, adjust_balance
from .test_helpers import *


class TestBalanceManager(TestCase):
    def setUp(self):
        setup_company_config()
        self.dept = create_test_department()
        self.desg = create_test_designation()
        self.emp = create_test_employee(department=self.dept, designation=self.desg)
        self.lt = create_test_leave_type()

    def test_credit_balance(self):
        bal = credit_balance(self.emp, self.lt, 2026, Decimal('8.0'), 'CREDIT_BULK', 'Year start')
        self.assertEqual(bal.entitled, Decimal('8.0'))
        self.assertTrue(LeaveBalanceLedger.objects.filter(
            employee=self.emp, txn_type='CREDIT_BULK'
        ).exists())

    def test_adjust_positive(self):
        create_test_balance(self.emp, self.lt)
        bal = adjust_balance(self.emp, 'TEST-001', 'SL', 2, 'Bonus')
        self.assertEqual(bal.adjusted, Decimal('2'))

    def test_adjust_negative(self):
        create_test_balance(self.emp, self.lt)
        bal = adjust_balance(self.emp, 'TEST-001', 'SL', -1, 'Correction')
        self.assertEqual(bal.adjusted, Decimal('-1'))

    def test_ledger_running_balance(self):
        credit_balance(self.emp, self.lt, 2026, Decimal('8.0'), 'CREDIT_BULK')
        credit_balance(self.emp, self.lt, 2026, Decimal('2.0'), 'CREDIT_ADJUSTMENT')
        entries = LeaveBalanceLedger.objects.filter(employee=self.emp).order_by('created_at')
        self.assertEqual(entries.count(), 2)
        self.assertEqual(entries.last().running_balance, Decimal('10.0'))
