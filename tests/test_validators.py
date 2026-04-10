from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from leaves.validators.leave_validators import *
from leaves.models import LeaveRequest
from .test_helpers import *


class TestValidators(TestCase):
    def setUp(self):
        setup_company_config()
        self.dept = create_test_department()
        self.desg = create_test_designation()
        self.emp = create_test_employee(department=self.dept, designation=self.desg)
        self.lt = create_test_leave_type()
        self.balance = create_test_balance(self.emp, self.lt)

    def _request_data(self, **overrides):
        data = {
            'start_date': date.today() + timedelta(days=1),
            'end_date': date.today() + timedelta(days=1),
            'duration': Decimal('1.0'),
            'is_half_day': False,
            'half_day_period': None,
            'event_date': None,
            'reason': 'test',
            'document': None,
        }
        data.update(overrides)
        return data

    def _config(self, **overrides):
        config = {
            'entitlement_days': 8, 'block_application': False,
            'gender_restriction': None, 'probation_eligible': True,
            'min_service_days': 0, 'avail_window_days': None,
            'advance_notice_days': 0, 'can_apply_in_advance': True,
            'can_apply_retroactively': True, 'half_day_allowed': True,
            'document_required': False, 'document_required_after_days': 0,
            'consecutive_day_restriction': False,
        }
        config.update(overrides)
        return config

    def test_employee_active(self):
        ok, _ = validate_employee_active(self.emp, self.lt, {}, {})
        self.assertTrue(ok)

        self.emp.is_active = False
        ok, err = validate_employee_active(self.emp, self.lt, {}, {})
        self.assertFalse(ok)

    def test_leave_type_active(self):
        ok, _ = validate_leave_type_active(self.emp, self.lt, {}, {})
        self.assertTrue(ok)

        self.lt.is_active = False
        ok, err = validate_leave_type_active(self.emp, self.lt, {}, {})
        self.assertFalse(ok)

    def test_blocked_by_override(self):
        ok, _ = validate_not_blocked_by_override(self.emp, self.lt, {}, self._config())
        self.assertTrue(ok)

        ok, err = validate_not_blocked_by_override(self.emp, self.lt, {}, self._config(block_application=True))
        self.assertFalse(ok)

    def test_gender_eligibility(self):
        ok, _ = validate_gender_eligibility(self.emp, self.lt, {}, self._config(gender_restriction='M'))
        self.assertTrue(ok)

        ok, err = validate_gender_eligibility(self.emp, self.lt, {}, self._config(gender_restriction='F'))
        self.assertFalse(ok)

    def test_probation_eligibility(self):
        self.emp.probation_status = 'ON_PROBATION'
        ok, err = validate_probation_eligibility(self.emp, self.lt, {}, self._config(probation_eligible=False))
        self.assertFalse(ok)

        ok, _ = validate_probation_eligibility(self.emp, self.lt, {}, self._config(probation_eligible=True))
        self.assertTrue(ok)

    def test_min_service_days(self):
        ok, err = validate_min_service_days(self.emp, self.lt, {}, self._config(min_service_days=9999))
        self.assertFalse(ok)

    def test_advance_notice(self):
        rd = self._request_data(start_date=date.today())
        ok, err = validate_advance_notice(self.emp, self.lt, rd, self._config(advance_notice_days=5))
        self.assertFalse(ok)

    def test_balance_sufficient(self):
        rd = self._request_data(duration=Decimal('100.0'))
        ok, err = validate_balance_sufficient(self.emp, self.lt, rd, self._config())
        self.assertFalse(ok)

        rd = self._request_data(duration=Decimal('1.0'))
        ok, _ = validate_balance_sufficient(self.emp, self.lt, rd, self._config())
        self.assertTrue(ok)

    def test_half_day_rules(self):
        rd = self._request_data(is_half_day=True, half_day_period='AM')
        ok, _ = validate_half_day_rules(self.emp, self.lt, rd, self._config(half_day_allowed=True))
        self.assertTrue(ok)

        ok, err = validate_half_day_rules(self.emp, self.lt, rd, self._config(half_day_allowed=False))
        self.assertFalse(ok)

    def test_half_day_missing_period(self):
        rd = self._request_data(is_half_day=True, half_day_period=None)
        ok, err = validate_half_day_rules(self.emp, self.lt, rd, self._config())
        self.assertFalse(ok)

    def test_overlapping_am_pm_allowed(self):
        d = date.today() + timedelta(days=5)
        LeaveRequest.objects.create(
            employee=self.emp, leave_type=self.lt,
            start_date=d, end_date=d, duration_days=Decimal('0.5'),
            is_half_day=True, half_day_period='AM', reason='test', status='APPROVED',
        )
        rd = self._request_data(start_date=d, end_date=d, is_half_day=True, half_day_period='PM')
        ok, _ = validate_overlapping_requests(self.emp, self.lt, rd, self._config())
        self.assertTrue(ok)

    def test_overlapping_same_period_fails(self):
        d = date.today() + timedelta(days=5)
        LeaveRequest.objects.create(
            employee=self.emp, leave_type=self.lt,
            start_date=d, end_date=d, duration_days=Decimal('0.5'),
            is_half_day=True, half_day_period='AM', reason='test', status='APPROVED',
        )
        rd = self._request_data(start_date=d, end_date=d, is_half_day=True, half_day_period='AM')
        ok, err = validate_overlapping_requests(self.emp, self.lt, rd, self._config())
        self.assertFalse(ok)

    def test_weekend_only_check(self):
        rd = self._request_data(duration=Decimal('0'))
        ok, err = validate_weekend_only_check(self.emp, self.lt, rd, self._config())
        self.assertFalse(ok)
