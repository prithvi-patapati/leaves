from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from leaves.models import LeaveRequest, LeaveBalance, LeaveBalanceLedger, LeavePolicyVersion, EmployeeOverride
from leaves.services.leave_application import apply_leave
from leaves.services.leave_approval import approve_leave, reject_leave
from .test_helpers import *


class TestLeaveApproval(TestCase):
    def setUp(self):
        setup_company_config()
        self.dept = create_test_department()
        self.desg = create_test_designation()
        self.manager = create_test_employee(
            employee_id='MGR-001', first_name='Manager', last_name='Test',
            department=self.dept, designation=self.desg,
        )
        self.emp = create_test_employee(
            department=self.dept, designation=self.desg,
            reporting_manager=self.manager,
        )
        self.lt = create_test_leave_type()
        LeavePolicyVersion.objects.create(
            leave_type=self.lt, version=1, snapshot={}, change_summary='init', changed_via='API',
        )
        self.balance = create_test_balance(self.emp, self.lt)

    def _next_weekday(self, days_ahead=3):
        d = date.today() + timedelta(days=days_ahead)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d

    def test_approve_happy_path(self):
        d = self._next_weekday()
        req = apply_leave(self.emp, 'SL', d, d, 'Sick')
        approved = approve_leave(self.manager, req.id)
        self.assertEqual(approved.status, 'APPROVED')

        bal = LeaveBalance.objects.get(employee=self.emp, leave_type=self.lt, year=2026)
        self.assertEqual(bal.used, Decimal('1.0'))
        self.assertEqual(bal.pending, Decimal('0'))

    def test_reject_happy_path(self):
        d = self._next_weekday()
        req = apply_leave(self.emp, 'SL', d, d, 'Sick')
        rejected = reject_leave(self.manager, req.id, 'Not approved')
        self.assertEqual(rejected.status, 'REJECTED')

        bal = LeaveBalance.objects.get(employee=self.emp, leave_type=self.lt, year=2026)
        self.assertEqual(bal.pending, Decimal('0'))
        self.assertEqual(bal.used, Decimal('0'))

    def test_approve_wrong_person(self):
        other = create_test_employee(
            employee_id='OTHER-001', first_name='Other',
            department=self.dept, designation=self.desg,
        )
        d = self._next_weekday()
        req = apply_leave(self.emp, 'SL', d, d, 'Sick')
        with self.assertRaises(ValueError) as ctx:
            approve_leave(other, req.id)
        self.assertIn('not the current approver', str(ctx.exception))

    def test_approve_blocked_by_override(self):
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.lt,
            block_approval=True, effective_from=date.today(),
            reason='Test', created_via='API',
        )
        d = self._next_weekday()
        req = apply_leave(self.emp, 'SL', d, d, 'Sick')
        with self.assertRaises(ValueError) as ctx:
            approve_leave(self.manager, req.id)
        self.assertIn('blocked', str(ctx.exception))

    def test_ledger_entries_on_approve(self):
        d = self._next_weekday()
        req = apply_leave(self.emp, 'SL', d, d, 'Sick')
        approve_leave(self.manager, req.id)

        entries = LeaveBalanceLedger.objects.filter(employee=self.emp, leave_type=self.lt).order_by('created_at')
        types = [e.txn_type for e in entries]
        self.assertIn('HOLD_PENDING', types)
        self.assertIn('RELEASE_HOLD', types)
        self.assertIn('DEBIT_APPROVED', types)
