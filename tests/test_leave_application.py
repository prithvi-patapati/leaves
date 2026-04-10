from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from leaves.models import LeaveRequest, LeaveBalance, LeaveBalanceLedger, EmployeeOverride, LeavePolicyVersion
from leaves.services.leave_application import apply_leave, cancel_leave, validate_leave
from .test_helpers import *


class TestLeaveApplication(TestCase):
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

    def test_apply_leave_happy_path(self):
        d = self._next_weekday()
        req = apply_leave(self.emp, 'SL', d, d, 'Sick')
        self.assertEqual(req.status, 'PENDING')
        self.assertEqual(req.current_approver, self.manager)
        self.assertEqual(req.duration_days, Decimal('1.0'))

        # Balance should have pending hold
        bal = LeaveBalance.objects.get(employee=self.emp, leave_type=self.lt, year=2026)
        self.assertEqual(bal.pending, Decimal('1.0'))

        # Ledger entry
        self.assertTrue(LeaveBalanceLedger.objects.filter(
            employee=self.emp, txn_type='HOLD_PENDING'
        ).exists())

    def test_apply_insufficient_balance(self):
        self.balance.entitled = Decimal('0')
        self.balance.save()
        d = self._next_weekday()
        with self.assertRaises(ValueError) as ctx:
            apply_leave(self.emp, 'SL', d, d, 'Test')
        self.assertIn('Insufficient', str(ctx.exception))

    def test_apply_blocked_by_override(self):
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.lt,
            block_application=True, effective_from=date.today(),
            reason='Test', created_via='API',
        )
        d = self._next_weekday()
        with self.assertRaises(ValueError) as ctx:
            apply_leave(self.emp, 'SL', d, d, 'Test')
        self.assertIn('blocked', str(ctx.exception))

    def test_apply_half_day(self):
        d = self._next_weekday()
        req = apply_leave(self.emp, 'SL', d, d, 'Sick half', is_half_day=True, half_day_period='AM')
        self.assertEqual(req.duration_days, Decimal('0.5'))
        self.assertTrue(req.is_half_day)

    def test_cancel_pending(self):
        d = self._next_weekday()
        req = apply_leave(self.emp, 'SL', d, d, 'Sick')
        cancelled = cancel_leave(self.emp, req.id)
        self.assertEqual(cancelled.status, 'CANCELLED')

        bal = LeaveBalance.objects.get(employee=self.emp, leave_type=self.lt, year=2026)
        self.assertEqual(bal.pending, Decimal('0'))

    def test_cancel_approved(self):
        d = self._next_weekday()
        req = apply_leave(self.emp, 'SL', d, d, 'Sick')
        # Simulate approval
        req.status = 'APPROVED'
        bal = LeaveBalance.objects.get(employee=self.emp, leave_type=self.lt, year=2026)
        bal.pending -= req.duration_days
        bal.used += req.duration_days
        bal.save()
        req.save()

        cancelled = cancel_leave(self.emp, req.id)
        self.assertEqual(cancelled.status, 'CANCELLED')
        bal.refresh_from_db()
        self.assertEqual(bal.used, Decimal('0'))

    def test_cancel_others_leave_fails(self):
        other = create_test_employee(
            employee_id='OTHER-001', first_name='Other',
            department=self.dept, designation=self.desg,
        )
        d = self._next_weekday()
        req = apply_leave(self.emp, 'SL', d, d, 'Sick')
        with self.assertRaises(ValueError):
            cancel_leave(other, req.id)

    def test_validate_leave_dry_run(self):
        d = self._next_weekday()
        ok, err = validate_leave(self.emp, 'SL', d, d)
        self.assertTrue(ok)

    def test_idempotency(self):
        d = self._next_weekday()
        req1 = apply_leave(self.emp, 'SL', d, d, 'Sick', idempotency_key='test-key-1')
        req2 = apply_leave(self.emp, 'SL', d, d, 'Sick', idempotency_key='test-key-1')
        # Second call returns cached result (dict), not a new request
        self.assertEqual(LeaveRequest.objects.filter(employee=self.emp).count(), 1)
