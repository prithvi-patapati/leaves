"""
Gamyam HRMS — Comprehensive Test Suite
156 test cases across 18 categories.
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.db import IntegrityError
from django.db.models import ProtectedError, Count

from employees.models import (
    Department, Team, Designation, Employee, EmployeeChangeLog,
    OnboardingTemplate, PendingHRAction,
)
from leaves.models import (
    LeaveType, LeavePolicyVersion, EmployeeOverride, LeaveBalance,
    LeaveBalanceLedger, LeaveRequest, CompanyConfig, FallbackManager,
    BatchOperation, IdempotencyLog, PayrollAdjustmentPending,
)
from employees.services.employee_service import (
    add_employee, update_employee, confirm_employee,
    deactivate_employee, transfer_employee, get_employee, search_employees,
)
from employees.services.org_service import (
    create_department, create_team, add_to_team, remove_from_team,
    list_departments, list_teams,
)
from leaves.services.config_resolver import get_effective_config
from leaves.services.approver_resolver import determine_approver, get_hr_head, get_ceo
from leaves.services.duration_calculator import (
    calculate_leave_days, calculate_pro_rata_entitlement, get_leave_year,
)
from leaves.services.leave_application import apply_leave, cancel_leave, validate_leave
from leaves.services.leave_approval import approve_leave, reject_leave
from leaves.services.balance_manager import credit_balance, adjust_balance, get_balances
from leaves.services.policy_manager import (
    create_leave_type as create_lt_service, update_leave_type, deactivate_leave_type,
)
from leaves.services.override_manager import (
    create_override, remove_override, check_override_conflict, get_overrides,
)
from leaves.services.batch_manager import bulk_create_overrides, confirm_batch, rollback_batch
from leaves.services.hr_action_service import (
    get_pending, resolve_action, execute_suggested_action, create_nudge,
)
from leaves.services.accrual import run_monthly_accrual, run_bulk_credit
from leaves.services.year_end import run_year_end_processing
from leaves.services.idempotency import execute_with_idempotency
from leaves.validators.leave_validators import *


# ════════════════════════════════════════════════════════════
# Test Helpers
# ════════════════════════════════════════════════════════════

def _setup_company_config():
    CompanyConfig.objects.get_or_create(pk=1, defaults={
        'leave_year_start_month': 4, 'leave_year_start_day': 1,
        'working_days_per_week': 5, 'weekend_days': [5, 6],
        'max_optional_holidays_per_year': 3,
        'top_level_approval_mode': 'SELF_APPROVE_WITH_HR_NOTIFY',
    })


def _dept(code='ENG', name='Engineering'):
    return Department.objects.create(code=code, name=name)


def _desg(title='Software Engineer', level=3):
    return Designation.objects.create(title=title, level=level)


def _hr_desg():
    return Designation.objects.create(title='Senior HR Manager', level=6)


def _ceo_desg():
    return Designation.objects.create(title='CEO', level=9)


def _emp(eid, first='Test', last='User', dept=None, desg=None, **kw):
    defaults = {
        'email': f'{eid.lower().replace("-","_")}@test.co', 'gender': 'M',
        'date_of_joining': date(2024, 1, 1), 'employment_type': 'FULL_TIME',
        'probation_status': 'CONFIRMED',
    }
    defaults.update(kw)
    return Employee.objects.create(
        employee_id=eid, first_name=first, last_name=last,
        department=dept, designation=desg, **defaults,
    )


def _sl(code='SL', **kw):
    defaults = {
        'name': 'Sick Leave', 'entitlement_days': 8, 'credit_method': 'BULK',
        'approval_chain': ['REPORTING_MANAGER'], 'is_pro_rata': True,
        'half_day_allowed': True, 'probation_eligible': True,
        'can_apply_retroactively': True, 'can_apply_in_advance': True,
        'max_continuous_days_before_flag': 5,
    }
    defaults.update(kw)
    return LeaveType.objects.create(code=code, **defaults)


def _bal(emp, lt, year=2026, entitled=Decimal('8.0')):
    return LeaveBalance.objects.create(
        employee=emp, leave_type=lt, year=year, entitled=entitled,
    )


def _pv(lt, version=1):
    return LeavePolicyVersion.objects.create(
        leave_type=lt, version=version, snapshot={},
        change_summary='init', changed_via='API',
    )


def _next_wd(days_ahead=3):
    """Return next weekday at least days_ahead from today."""
    d = date.today() + timedelta(days=days_ahead)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _next_monday(days_ahead=7):
    d = date.today() + timedelta(days=days_ahead)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


def _config(**overrides):
    c = {
        'entitlement_days': 8, 'block_application': False,
        'block_approval': False, 'block_accrual': False,
        'gender_restriction': None, 'probation_eligible': True,
        'min_service_days': 0, 'avail_window_days': None,
        'advance_notice_days': 0, 'can_apply_in_advance': True,
        'can_apply_retroactively': True, 'half_day_allowed': True,
        'document_required': False, 'document_required_after_days': 0,
        'consecutive_day_restriction': False,
        'max_continuous_days_before_flag': None,
        'approval_chain': ['REPORTING_MANAGER'],
    }
    c.update(overrides)
    return c


def _rd(**overrides):
    d = _next_wd()
    data = {
        'start_date': d, 'end_date': d, 'duration': Decimal('1.0'),
        'is_half_day': False, 'half_day_period': None,
        'event_date': None, 'reason': 'test', 'document': None,
    }
    data.update(overrides)
    return data


# ════════════════════════════════════════════════════════════
# Category 1: Employee Model & Lifecycle (12 cases)
# ════════════════════════════════════════════════════════════

class Cat01_EmployeeLifecycle(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()

    def test_1_1_create_employee_all_fields(self):
        mgr = _emp('MGR-01', 'Mgr', dept=self.dept, desg=self.desg)
        emp = _emp('E-01', 'Prithvi', 'Patapati', dept=self.dept, desg=self.desg,
                   reporting_manager=mgr, phone='1234567890',
                   date_of_birth=date(1995, 5, 15))
        self.assertEqual(emp.full_name, 'Prithvi Patapati')
        self.assertTrue(emp.is_active)
        self.assertEqual(emp.reporting_manager, mgr)

    def test_1_2_unique_employee_id(self):
        _emp('DUP-01', dept=self.dept, desg=self.desg)
        with self.assertRaises(IntegrityError):
            _emp('DUP-01', dept=self.dept, desg=self.desg, email='dup2@test.co')

    def test_1_3_unique_email(self):
        _emp('A-01', dept=self.dept, desg=self.desg, email='same@test.co')
        with self.assertRaises(IntegrityError):
            _emp('A-02', dept=self.dept, desg=self.desg, email='same@test.co')

    def test_1_4_service_days_property(self):
        emp = _emp('SD-01', dept=self.dept, desg=self.desg,
                   date_of_joining=date.today() - timedelta(days=100))
        self.assertEqual(emp.service_days, 100)

    def test_1_5_is_on_probation(self):
        emp = _emp('PR-01', dept=self.dept, desg=self.desg, probation_status='ON_PROBATION')
        self.assertTrue(emp.is_on_probation)
        emp.probation_status = 'CONFIRMED'
        self.assertFalse(emp.is_on_probation)

    def test_1_6_confirm_employee(self):
        emp, _ = add_employee(
            employee_id='CF-01', first_name='Conf', email='cf01@test.co',
            gender='M', department=self.dept, designation=self.desg,
            date_of_joining=date(2024, 1, 1), probation_status='ON_PROBATION',
        )
        result = confirm_employee(None, 'CF-01')
        self.assertEqual(result.probation_status, 'CONFIRMED')
        self.assertEqual(result.confirmation_date, date.today())

    def test_1_7_deactivate_employee(self):
        emp, _ = add_employee(
            employee_id='EX-01', first_name='Exit', email='ex01@test.co',
            gender='M', department=self.dept, designation=self.desg,
            date_of_joining=date(2024, 1, 1),
        )
        result = deactivate_employee(None, 'EX-01', date.today(), 'RESIGNED')
        self.assertFalse(result.is_active)
        self.assertEqual(result.last_working_date, date.today())
        self.assertEqual(result.exit_reason, 'RESIGNED')

    def test_1_8_transfer_dept_change(self):
        dept2 = _dept('SALES', 'Sales')
        emp, _ = add_employee(
            employee_id='TR-01', first_name='Transfer', email='tr01@test.co',
            gender='M', department=self.dept, designation=self.desg,
            date_of_joining=date(2024, 1, 1),
        )
        transfer_employee(None, 'TR-01', department=dept2)
        emp.refresh_from_db()
        self.assertEqual(emp.department, dept2)
        log = EmployeeChangeLog.objects.filter(employee=emp, field_changed='department')
        self.assertTrue(log.exists())

    def test_1_9_transfer_manager_change(self):
        mgr1 = _emp('M1', 'Mgr1', dept=self.dept, desg=self.desg)
        mgr2 = _emp('M2', 'Mgr2', dept=self.dept, desg=self.desg)
        emp, _ = add_employee(
            employee_id='TR-02', first_name='Transfer2', email='tr02@test.co',
            gender='M', department=self.dept, designation=self.desg,
            date_of_joining=date(2024, 1, 1), reporting_manager=mgr1,
        )
        transfer_employee(None, 'TR-02', reporting_manager=mgr2)
        log = EmployeeChangeLog.objects.filter(employee=emp, field_changed='reporting_manager')
        self.assertTrue(log.exists())

    def test_1_10_transfer_multiple_fields(self):
        dept2 = _dept('MKT', 'Marketing')
        desg2 = _desg('Senior Software Engineer', 4)
        emp, _ = add_employee(
            employee_id='TR-03', first_name='Multi', email='tr03@test.co',
            gender='M', department=self.dept, designation=self.desg,
            date_of_joining=date(2024, 1, 1),
        )
        transfer_employee(None, 'TR-03', department=dept2, designation=desg2)
        logs = EmployeeChangeLog.objects.filter(employee=emp)
        field_names = set(logs.values_list('field_changed', flat=True))
        self.assertIn('department', field_names)
        self.assertIn('designation', field_names)

    def test_1_11_add_to_multiple_teams(self):
        t1 = Team.objects.create(code='T1', name='Team1')
        t2 = Team.objects.create(code='T2', name='Team2')
        emp = _emp('TM-01', dept=self.dept, desg=self.desg)
        emp.teams.add(t1, t2)
        self.assertEqual(emp.teams.count(), 2)

    def test_1_12_delete_dept_with_employees_fails(self):
        _emp('PF-01', dept=self.dept, desg=self.desg)
        with self.assertRaises(ProtectedError):
            self.dept.delete()


# ════════════════════════════════════════════════════════════
# Category 2: Department & Team CRUD (8 cases)
# ════════════════════════════════════════════════════════════

class Cat02_DeptTeamCRUD(TestCase):
    def setUp(self):
        self.dept = _dept()
        self.desg = _desg()

    def test_2_1_create_department(self):
        d = create_department('Sales', 'SALES')
        self.assertEqual(d.name, 'Sales')
        self.assertTrue(d.is_active)

    def test_2_2_duplicate_department_code(self):
        create_department('Sales', 'SALES')
        with self.assertRaises(IntegrityError):
            create_department('Sales2', 'SALES')

    def test_2_3_deactivate_department(self):
        d = create_department('Ops', 'OPS')
        emp = _emp('DO-01', dept=d, desg=self.desg)
        d.is_active = False
        d.save()
        emp.refresh_from_db()
        self.assertTrue(emp.is_active)

    def test_2_4_create_team(self):
        t = create_team('Practo', 'PRACTO')
        self.assertEqual(t.name, 'Practo')
        self.assertTrue(t.is_active)

    def test_2_5_add_employee_to_team(self):
        t = create_team('T1', 'T1')
        _emp('TE-01', dept=self.dept, desg=self.desg)
        add_to_team('TE-01', 'T1')
        self.assertTrue(t.members.filter(employee_id='TE-01').exists())

    def test_2_6_remove_employee_from_team(self):
        t = create_team('T2', 'T2')
        _emp('TE-02', dept=self.dept, desg=self.desg)
        add_to_team('TE-02', 'T2')
        remove_from_team('TE-02', 'T2')
        self.assertFalse(t.members.filter(employee_id='TE-02').exists())

    def test_2_7_list_depts_with_counts(self):
        d2 = _dept('HR', 'Human Resources')
        _emp('LC-01', dept=self.dept, desg=self.desg)
        _emp('LC-02', dept=self.dept, desg=self.desg)
        _emp('LC-03', dept=d2, desg=self.desg)
        depts = list_departments()
        eng = depts.get(code='ENG')
        self.assertEqual(eng.employee_count, 2)

    def test_2_8_list_teams_with_counts(self):
        t = create_team('TCount', 'TC')
        _emp('TC-01', dept=self.dept, desg=self.desg)
        _emp('TC-02', dept=self.dept, desg=self.desg)
        add_to_team('TC-01', 'TC')
        add_to_team('TC-02', 'TC')
        teams = list_teams()
        tc = teams.get(code='TC')
        self.assertEqual(tc.member_count, 2)


# ════════════════════════════════════════════════════════════
# Category 3: Config Resolver (14 cases)
# ════════════════════════════════════════════════════════════

class Cat03_ConfigResolver(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.emp = _emp('CR-01', dept=self.dept, desg=self.desg)
        self.lt = _sl()

    def _override(self, **kw):
        defaults = {
            'employee': self.emp, 'leave_type': self.lt,
            'effective_from': date.today(), 'reason': 'test', 'created_via': 'API',
        }
        defaults.update(kw)
        return EmployeeOverride.objects.create(**defaults)

    def test_3_1_no_override_base_config(self):
        c = get_effective_config(self.emp, self.lt)
        self.assertEqual(c['entitlement_days'], 8)
        self.assertFalse(c['block_accrual'])
        self.assertFalse(c['block_application'])
        self.assertFalse(c['block_approval'])
        self.assertEqual(c['approval_chain'], ['REPORTING_MANAGER'])

    def test_3_2_block_accrual(self):
        self._override(block_accrual=True)
        self.assertTrue(get_effective_config(self.emp, self.lt)['block_accrual'])

    def test_3_3_block_application(self):
        self._override(block_application=True)
        self.assertTrue(get_effective_config(self.emp, self.lt)['block_application'])

    def test_3_4_modify_entitlement(self):
        self._override(modify_entitlement=Decimal('10.0'))
        self.assertEqual(get_effective_config(self.emp, self.lt)['entitlement_days'], Decimal('10.0'))

    def test_3_5_waive_restriction(self):
        lt = _sl(code='WFH2', name='WFH', probation_eligible=False)
        self._override(leave_type=lt, waive_restriction={'probation_eligible': True})
        self.assertTrue(get_effective_config(self.emp, lt)['probation_eligible'])

    def test_3_6_custom_approval_chain(self):
        self._override(custom_approval_chain=['HR'])
        self.assertEqual(get_effective_config(self.emp, self.lt)['approval_chain'], ['HR'])

    def test_3_7_expired_override_ignored(self):
        self._override(block_application=True,
                       effective_from=date.today() - timedelta(days=30),
                       effective_to=date.today() - timedelta(days=1))
        self.assertFalse(get_effective_config(self.emp, self.lt)['block_application'])

    def test_3_8_future_override_ignored(self):
        self._override(block_application=True,
                       effective_from=date.today() + timedelta(days=10))
        self.assertFalse(get_effective_config(self.emp, self.lt)['block_application'])

    def test_3_9_override_active_today_edge(self):
        self._override(block_application=True,
                       effective_from=date.today(), effective_to=date.today())
        self.assertTrue(get_effective_config(self.emp, self.lt)['block_application'])

    def test_3_10_permanent_override_no_end(self):
        self._override(block_application=True, effective_to=None)
        self.assertTrue(get_effective_config(self.emp, self.lt)['block_application'])

    def test_3_11_multiple_overrides_latest_wins(self):
        self._override(modify_entitlement=Decimal('5.0'))
        self._override(modify_entitlement=Decimal('12.0'))
        self.assertEqual(get_effective_config(self.emp, self.lt)['entitlement_days'], Decimal('12.0'))

    def test_3_12_null_leave_type_applies_to_all(self):
        self._override(leave_type=None, block_application=True)
        self.assertTrue(get_effective_config(self.emp, self.lt)['block_application'])
        lt2 = _sl(code='PL2', name='PL')
        self.assertTrue(get_effective_config(self.emp, lt2)['block_application'])

    def test_3_13_non_overridden_fields_kept(self):
        self._override(block_accrual=True)
        c = get_effective_config(self.emp, self.lt)
        self.assertTrue(c['block_accrual'])
        self.assertEqual(c['half_day_allowed'], self.lt.half_day_allowed)
        self.assertEqual(c['advance_notice_days'], self.lt.advance_notice_days)

    def test_3_14_override_specific_type_no_leak(self):
        lt2 = _sl(code='PL3', name='PL')
        self._override(leave_type=self.lt, block_application=True)
        self.assertTrue(get_effective_config(self.emp, self.lt)['block_application'])
        self.assertFalse(get_effective_config(self.emp, lt2)['block_application'])


# ════════════════════════════════════════════════════════════
# Category 4: Validators (34 cases)
# ════════════════════════════════════════════════════════════

class Cat04a_BasicValidators(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.emp = _emp('V-01', dept=self.dept, desg=self.desg)
        self.lt = _sl()

    def test_4_1_active_employee_passes(self):
        ok, _ = validate_employee_active(self.emp, self.lt, {}, {})
        self.assertTrue(ok)

    def test_4_2_inactive_employee_fails(self):
        self.emp.is_active = False
        ok, err = validate_employee_active(self.emp, self.lt, {}, {})
        self.assertFalse(ok)
        self.assertIn('not active', err)

    def test_4_3_active_leave_type_passes(self):
        ok, _ = validate_leave_type_active(self.emp, self.lt, {}, {})
        self.assertTrue(ok)

    def test_4_4_deactivated_leave_type_fails(self):
        self.lt.is_active = False
        ok, err = validate_leave_type_active(self.emp, self.lt, {}, {})
        self.assertFalse(ok)

    def test_4_5_no_override_block_passes(self):
        ok, _ = validate_not_blocked_by_override(self.emp, self.lt, {}, _config())
        self.assertTrue(ok)

    def test_4_6_override_block_application_fails(self):
        ok, err = validate_not_blocked_by_override(
            self.emp, self.lt, {}, _config(block_application=True))
        self.assertFalse(ok)
        self.assertIn('blocked', err)


class Cat04b_EligibilityValidators(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()

    def test_4_7_male_applying_ML_fails(self):
        emp = _emp('V-07', dept=self.dept, desg=self.desg, gender='M')
        lt = _sl(code='ML2', name='Maternity Leave', gender_restriction='F')
        ok, err = validate_gender_eligibility(emp, lt, {}, _config(gender_restriction='F'))
        self.assertFalse(ok)
        self.assertIn("'F'", err)

    def test_4_8_female_applying_ML_passes(self):
        emp = _emp('V-08', dept=self.dept, desg=self.desg, gender='F')
        lt = _sl(code='ML3', name='Maternity', gender_restriction='F')
        ok, _ = validate_gender_eligibility(emp, lt, {}, _config(gender_restriction='F'))
        self.assertTrue(ok)

    def test_4_9_male_applying_PtL_passes(self):
        emp = _emp('V-09', dept=self.dept, desg=self.desg, gender='M')
        ok, _ = validate_gender_eligibility(emp, self._ptl(), {}, _config(gender_restriction='M'))
        self.assertTrue(ok)

    def test_4_10_female_applying_PtL_fails(self):
        emp = _emp('V-10', dept=self.dept, desg=self.desg, gender='F')
        ok, err = validate_gender_eligibility(emp, self._ptl(), {}, _config(gender_restriction='M'))
        self.assertFalse(ok)

    def _ptl(self):
        return _sl(code='PTL2', name='Paternity Leave', gender_restriction='M')

    def test_4_11_probation_WFH_fails(self):
        emp = _emp('V-11', dept=self.dept, desg=self.desg, probation_status='ON_PROBATION')
        lt = _sl(code='WFH3', name='WFH', probation_eligible=False)
        ok, err = validate_probation_eligibility(emp, lt, {}, _config(probation_eligible=False))
        self.assertFalse(ok)
        self.assertIn('probation', err.lower())

    def test_4_12_confirmed_WFH_passes(self):
        emp = _emp('V-12', dept=self.dept, desg=self.desg, probation_status='CONFIRMED')
        ok, _ = validate_probation_eligibility(emp, _sl(), {}, _config(probation_eligible=False))
        self.assertTrue(ok)

    def test_4_13_probation_SL_passes(self):
        emp = _emp('V-13', dept=self.dept, desg=self.desg, probation_status='ON_PROBATION')
        ok, _ = validate_probation_eligibility(emp, _sl(), {}, _config(probation_eligible=True))
        self.assertTrue(ok)

    def test_4_14_min_service_50_needs_80_fails(self):
        emp = _emp('V-14', dept=self.dept, desg=self.desg,
                   date_of_joining=date.today() - timedelta(days=50))
        ok, err = validate_min_service_days(emp, _sl(), {}, _config(min_service_days=80))
        self.assertFalse(ok)
        self.assertIn('80', err)

    def test_4_15_min_service_100_needs_80_passes(self):
        emp = _emp('V-15', dept=self.dept, desg=self.desg,
                   date_of_joining=date.today() - timedelta(days=100))
        ok, _ = validate_min_service_days(emp, _sl(), {}, _config(min_service_days=80))
        self.assertTrue(ok)


class Cat04c_TimingValidators(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.emp = _emp('VT-01', dept=self.dept, desg=self.desg)
        self.lt = _sl()

    def test_4_16_PL_1_day_notice_fails(self):
        rd = _rd(start_date=date.today() + timedelta(days=1))
        ok, _ = validate_advance_notice(self.emp, self.lt, rd, _config(advance_notice_days=2))
        self.assertFalse(ok)

    def test_4_17_PL_3_days_notice_passes(self):
        rd = _rd(start_date=date.today() + timedelta(days=3))
        ok, _ = validate_advance_notice(self.emp, self.lt, rd, _config(advance_notice_days=2))
        self.assertTrue(ok)

    def test_4_18_SL_applied_in_advance_fails(self):
        rd = _rd(start_date=date.today() + timedelta(days=7))
        ok, _ = validate_advance_application_policy(
            self.emp, self.lt, rd, _config(can_apply_in_advance=False))
        self.assertFalse(ok)

    def test_4_19_SL_retroactive_passes(self):
        rd = _rd(start_date=date.today() - timedelta(days=1),
                 end_date=date.today() - timedelta(days=1))
        ok, _ = validate_retroactive_policy(
            self.emp, self.lt, rd, _config(can_apply_retroactively=True))
        self.assertTrue(ok)

    def test_4_20_PL_retroactive_fails(self):
        rd = _rd(start_date=date.today() - timedelta(days=2),
                 end_date=date.today() - timedelta(days=1))
        ok, _ = validate_retroactive_policy(
            self.emp, self.lt, rd, _config(can_apply_retroactively=False))
        self.assertFalse(ok)

    def test_4_21_PtL_outside_90_day_window_fails(self):
        event = date.today() - timedelta(days=100)
        rd = _rd(event_date=event, start_date=date.today())
        ok, err = validate_avail_window(self.emp, self.lt, rd, _config(avail_window_days=90))
        self.assertFalse(ok)
        self.assertIn('90', err)


class Cat04d_BalanceValidators(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.emp = _emp('VB-01', dept=self.dept, desg=self.desg)
        self.lt = _sl()

    def test_4_22_sufficient_balance_passes(self):
        _bal(self.emp, self.lt, entitled=Decimal('5.0'))
        rd = _rd(duration=Decimal('3.0'))
        ok, _ = validate_balance_sufficient(self.emp, self.lt, rd, _config())
        self.assertTrue(ok)

    def test_4_23_insufficient_balance_fails(self):
        _bal(self.emp, self.lt, entitled=Decimal('2.0'))
        rd = _rd(duration=Decimal('3.0'))
        ok, err = validate_balance_sufficient(self.emp, self.lt, rd, _config())
        self.assertFalse(ok)
        self.assertIn('Insufficient', err)

    def test_4_24_LOP_always_passes(self):
        lop = _sl(code='LOP2', name='LOP', credit_method='ON_DEMAND', entitlement_days=0)
        rd = _rd(duration=Decimal('10.0'))
        ok, _ = validate_balance_sufficient(self.emp, lop, rd, _config())
        self.assertTrue(ok)

    def test_4_25_EVENT_always_passes(self):
        bl = _sl(code='BL2', name='BL', credit_method='EVENT', entitlement_days=5)
        rd = _rd(duration=Decimal('3.0'))
        ok, _ = validate_balance_sufficient(self.emp, bl, rd, _config())
        self.assertTrue(ok)

    def test_4_26_exact_balance_passes(self):
        _bal(self.emp, self.lt, entitled=Decimal('3.0'))
        rd = _rd(duration=Decimal('3.0'))
        ok, _ = validate_balance_sufficient(self.emp, self.lt, rd, _config())
        self.assertTrue(ok)


class Cat04e_HalfDayValidators(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.emp = _emp('VH-01', dept=self.dept, desg=self.desg)
        self.lt = _sl()

    def test_4_27_half_day_allowed_passes(self):
        d = _next_wd()
        rd = _rd(start_date=d, end_date=d, is_half_day=True, half_day_period='AM')
        ok, _ = validate_half_day_rules(self.emp, self.lt, rd, _config(half_day_allowed=True))
        self.assertTrue(ok)

    def test_4_28_half_day_not_allowed_fails(self):
        d = _next_wd()
        rd = _rd(start_date=d, end_date=d, is_half_day=True, half_day_period='AM')
        ok, _ = validate_half_day_rules(self.emp, self.lt, rd, _config(half_day_allowed=False))
        self.assertFalse(ok)

    def test_4_29_half_day_no_period_fails(self):
        d = _next_wd()
        rd = _rd(start_date=d, end_date=d, is_half_day=True, half_day_period=None)
        ok, _ = validate_half_day_rules(self.emp, self.lt, rd, _config())
        self.assertFalse(ok)

    def test_4_30_half_day_multi_day_fails(self):
        d = _next_wd()
        rd = _rd(start_date=d, end_date=d + timedelta(days=1), is_half_day=True, half_day_period='AM')
        ok, err = validate_half_day_rules(self.emp, self.lt, rd, _config())
        self.assertFalse(ok)
        self.assertIn('single day', err)


class Cat04f_OverlapValidators(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.emp = _emp('VO-01', dept=self.dept, desg=self.desg)
        self.lt = _sl()

    def _req(self, start, end, status='APPROVED', is_half_day=False, period=None, dur=None):
        return LeaveRequest.objects.create(
            employee=self.emp, leave_type=self.lt,
            start_date=start, end_date=end,
            duration_days=dur or (Decimal('0.5') if is_half_day else Decimal('1.0')),
            is_half_day=is_half_day, half_day_period=period,
            reason='test', status=status,
        )

    def test_4_31_full_overlap_fails(self):
        d = _next_wd(5)
        self._req(d, d + timedelta(days=2), dur=Decimal('3'))
        rd = _rd(start_date=d, end_date=d + timedelta(days=1), duration=Decimal('2'))
        ok, _ = validate_overlapping_requests(self.emp, self.lt, rd, _config())
        self.assertFalse(ok)

    def test_4_32_AM_PM_same_date_passes(self):
        d = _next_wd(5)
        self._req(d, d, is_half_day=True, period='AM')
        rd = _rd(start_date=d, end_date=d, is_half_day=True, half_day_period='PM')
        ok, _ = validate_overlapping_requests(self.emp, self.lt, rd, _config())
        self.assertTrue(ok)

    def test_4_33_AM_AM_same_date_fails(self):
        d = _next_wd(5)
        self._req(d, d, is_half_day=True, period='AM')
        rd = _rd(start_date=d, end_date=d, is_half_day=True, half_day_period='AM')
        ok, _ = validate_overlapping_requests(self.emp, self.lt, rd, _config())
        self.assertFalse(ok)

    def test_4_34_half_then_full_fails(self):
        d = _next_wd(5)
        self._req(d, d, is_half_day=True, period='AM')
        rd = _rd(start_date=d, end_date=d, is_half_day=False)
        ok, _ = validate_overlapping_requests(self.emp, self.lt, rd, _config())
        self.assertFalse(ok)

    def test_4_35_full_then_half_fails(self):
        d = _next_wd(5)
        self._req(d, d, is_half_day=False)
        rd = _rd(start_date=d, end_date=d, is_half_day=True, half_day_period='AM')
        ok, _ = validate_overlapping_requests(self.emp, self.lt, rd, _config())
        self.assertFalse(ok)

    def test_4_36_non_overlapping_passes(self):
        d = _next_wd(5)
        self._req(d, d + timedelta(days=1), dur=Decimal('2'))
        d2 = d + timedelta(days=3)
        rd = _rd(start_date=d2, end_date=d2 + timedelta(days=1))
        ok, _ = validate_overlapping_requests(self.emp, self.lt, rd, _config())
        self.assertTrue(ok)

    def test_4_37_pending_also_blocks(self):
        d = _next_wd(5)
        self._req(d, d, status='PENDING')
        rd = _rd(start_date=d, end_date=d)
        ok, _ = validate_overlapping_requests(self.emp, self.lt, rd, _config())
        self.assertFalse(ok)

    def test_4_38_cancelled_doesnt_block(self):
        d = _next_wd(5)
        self._req(d, d, status='CANCELLED')
        rd = _rd(start_date=d, end_date=d)
        ok, _ = validate_overlapping_requests(self.emp, self.lt, rd, _config())
        self.assertTrue(ok)


class Cat04g_OtherValidators(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.emp = _emp('VG-01', dept=self.dept, desg=self.desg)
        self.lt = _sl(code='WFH5', name='WFH', consecutive_day_restriction=True)

    def test_4_39_wfh_consecutive_restriction(self):
        mon = _next_monday()
        LeaveRequest.objects.create(
            employee=self.emp, leave_type=self.lt,
            start_date=mon, end_date=mon, duration_days=Decimal('1'),
            reason='test', status='APPROVED',
        )
        tue = mon + timedelta(days=1)
        rd = _rd(start_date=tue, end_date=tue)
        ok, err = validate_consecutive_restriction(
            self.emp, self.lt, rd, _config(consecutive_day_restriction=True))
        self.assertFalse(ok)

    def test_4_40_all_weekend_dates_fails(self):
        rd = _rd(duration=Decimal('0'), is_half_day=False)
        ok, _ = validate_weekend_only_check(self.emp, self.lt, rd, _config())
        self.assertFalse(ok)


# ════════════════════════════════════════════════════════════
# Category 5: Leave Application Flow (16 cases)
# ════════════════════════════════════════════════════════════

class Cat05_LeaveApplication(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.mgr = _emp('M-05', 'Manager', dept=self.dept, desg=self.desg)
        self.emp = _emp('E-05', 'Emp', dept=self.dept, desg=self.desg,
                        reporting_manager=self.mgr)
        self.lt = _sl()
        _pv(self.lt)
        self.bal = _bal(self.emp, self.lt)

    def test_5_1_happy_path(self):
        d = _next_wd()
        req = apply_leave(self.emp, 'SL', d, d, 'Sick')
        self.assertEqual(req.status, 'PENDING')
        self.assertEqual(req.current_approver, self.mgr)
        self.bal.refresh_from_db()
        self.assertEqual(self.bal.pending, Decimal('1.0'))
        self.assertTrue(LeaveBalanceLedger.objects.filter(
            employee=self.emp, txn_type='HOLD_PENDING').exists())

    def test_5_2_duration_excludes_weekends(self):
        mon = _next_monday()
        fri = mon + timedelta(days=4)
        self.assertEqual(calculate_leave_days(mon, fri, False), Decimal('5'))

    def test_5_3_duration_mon_to_sun(self):
        mon = _next_monday()
        sun = mon + timedelta(days=6)
        self.assertEqual(calculate_leave_days(mon, sun, False), Decimal('5'))

    def test_5_4_half_day(self):
        d = _next_wd()
        req = apply_leave(self.emp, 'SL', d, d, 'half',
                          is_half_day=True, half_day_period='AM')
        self.assertEqual(req.duration_days, Decimal('0.5'))
        self.bal.refresh_from_db()
        self.assertEqual(self.bal.pending, Decimal('0.5'))

    def test_5_5_policy_version_snapshot(self):
        d = _next_wd()
        req = apply_leave(self.emp, 'SL', d, d, 'test')
        self.assertIsNotNone(req.policy_version)
        self.assertEqual(req.policy_version.version, 1)

    def test_5_6_approver_correct(self):
        d = _next_wd()
        req = apply_leave(self.emp, 'SL', d, d, 'test')
        self.assertEqual(req.current_approver, self.mgr)

    def test_5_7_fallback_manager(self):
        fb = _emp('FB-05', 'Fallback', dept=self.dept, desg=self.desg)
        LeaveRequest.objects.create(
            employee=self.mgr, leave_type=self.lt,
            start_date=date.today(), end_date=date.today() + timedelta(days=5),
            duration_days=5, reason='vac', status='APPROVED',
        )
        FallbackManager.objects.create(
            employee=self.emp, primary_manager=self.mgr, fallback_manager=fb,
            effective_from=date.today(), is_active=True,
        )
        d = _next_wd()
        req = apply_leave(self.emp, 'SL', d, d, 'test')
        self.assertEqual(req.current_approver, fb)

    def test_5_8_ceo_self_approval(self):
        hr_dept = _dept('HR5', 'HR')
        _emp('HR-05', 'HR', dept=hr_dept, desg=_hr_desg())
        ceo = _emp('CEO-05', 'CEO', dept=self.dept, desg=_ceo_desg(), reporting_manager=None)
        _bal(ceo, self.lt)
        d = _next_wd()
        req = apply_leave(ceo, 'SL', d, d, 'test')
        self.assertEqual(req.current_approver, ceo)

    def test_5_9_idempotency_same_key(self):
        d = _next_wd()
        apply_leave(self.emp, 'SL', d, d, 'Sick', idempotency_key='idem-5-9')
        apply_leave(self.emp, 'SL', d, d, 'Sick', idempotency_key='idem-5-9')
        self.assertEqual(LeaveRequest.objects.filter(employee=self.emp).count(), 1)

    def test_5_10_different_key_creates_new(self):
        d = _next_wd()
        d2 = _next_wd(5)
        apply_leave(self.emp, 'SL', d, d, 'Sick', idempotency_key='idem-5-10a')
        apply_leave(self.emp, 'SL', d2, d2, 'Sick', idempotency_key='idem-5-10b')
        self.assertEqual(LeaveRequest.objects.filter(employee=self.emp).count(), 2)

    def test_5_11_insufficient_balance_fails(self):
        self.bal.entitled = Decimal('0')
        self.bal.save()
        d = _next_wd()
        with self.assertRaises(ValueError) as ctx:
            apply_leave(self.emp, 'SL', d, d, 'test')
        self.assertIn('Insufficient', str(ctx.exception))
        self.assertEqual(LeaveRequest.objects.filter(employee=self.emp).count(), 0)

    def test_5_12_blocked_type_fails(self):
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.lt,
            block_application=True, effective_from=date.today(),
            reason='blocked', created_via='API',
        )
        d = _next_wd()
        with self.assertRaises(ValueError) as ctx:
            apply_leave(self.emp, 'SL', d, d, 'test')
        self.assertIn('blocked', str(ctx.exception))

    @patch('leaves.services.leave_application.signals')
    def test_5_13_signal_triggered(self, mock_signals):
        d = _next_wd()
        apply_leave(self.emp, 'SL', d, d, 'test')
        mock_signals.leave_applied.send.assert_called_once()

    def test_5_14_cancel_pending(self):
        d = _next_wd()
        req = apply_leave(self.emp, 'SL', d, d, 'test')
        cancel_leave(self.emp, req.id)
        self.bal.refresh_from_db()
        self.assertEqual(self.bal.pending, Decimal('0'))
        self.assertTrue(LeaveBalanceLedger.objects.filter(
            employee=self.emp, txn_type='RELEASE_HOLD').exists())

    def test_5_15_cancel_approved(self):
        d = _next_wd()
        req = apply_leave(self.emp, 'SL', d, d, 'test')
        approve_leave(self.mgr, req.id)
        cancel_leave(self.emp, req.id)
        self.bal.refresh_from_db()
        self.assertEqual(self.bal.used, Decimal('0'))
        self.assertTrue(LeaveBalanceLedger.objects.filter(
            employee=self.emp, txn_type='CREDIT_REVERSAL').exists())

    def test_5_16_cancel_others_fails(self):
        other = _emp('OT-05', 'Other', dept=self.dept, desg=self.desg)
        d = _next_wd()
        req = apply_leave(self.emp, 'SL', d, d, 'test')
        with self.assertRaises(ValueError):
            cancel_leave(other, req.id)


# ════════════════════════════════════════════════════════════
# Category 6: Leave Approval Flow (12 cases)
# ════════════════════════════════════════════════════════════

class Cat06_LeaveApproval(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.hr_dept = _dept('HRD', 'HR')
        self.desg = _desg()
        self.hr = _emp('HR-06', 'HR', 'Head', dept=self.hr_dept, desg=_hr_desg())
        self.mgr = _emp('M-06', 'Mgr', dept=self.dept, desg=self.desg)
        self.emp = _emp('E-06', 'Emp', dept=self.dept, desg=self.desg,
                        reporting_manager=self.mgr)
        self.lt = _sl()
        _pv(self.lt)
        self.bal = _bal(self.emp, self.lt)

    def _apply(self, d=None):
        return apply_leave(self.emp, 'SL', d or _next_wd(), d or _next_wd(), 'test')

    def test_6_1_approve_happy(self):
        req = self._apply()
        r = approve_leave(self.mgr, req.id)
        self.assertEqual(r.status, 'APPROVED')
        self.assertEqual(r.approved_by, self.mgr)
        self.assertIsNotNone(r.approved_at)
        self.bal.refresh_from_db()
        self.assertEqual(self.bal.used, Decimal('1'))
        self.assertEqual(self.bal.pending, Decimal('0'))
        self.assertTrue(LeaveBalanceLedger.objects.filter(
            employee=self.emp, txn_type='DEBIT_APPROVED').exists())

    def test_6_2_reject_happy(self):
        req = self._apply()
        r = reject_leave(self.mgr, req.id, 'No')
        self.assertEqual(r.status, 'REJECTED')
        self.assertEqual(r.rejected_by, self.mgr)
        self.assertEqual(r.rejection_remarks, 'No')
        self.bal.refresh_from_db()
        self.assertEqual(self.bal.pending, Decimal('0'))
        self.assertEqual(self.bal.used, Decimal('0'))

    def test_6_3_approve_wrong_person_fails(self):
        other = _emp('WP-06', 'Wrong', dept=self.dept, desg=self.desg)
        req = self._apply()
        with self.assertRaises(ValueError) as ctx:
            approve_leave(other, req.id)
        self.assertIn('not the current approver', str(ctx.exception))

    def test_6_4_reject_empty_remarks(self):
        req = self._apply()
        r = reject_leave(self.mgr, req.id, '')
        self.assertEqual(r.status, 'REJECTED')

    def test_6_5_approve_blocked_by_override(self):
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.lt,
            block_approval=True, effective_from=date.today(),
            reason='block', created_via='API',
        )
        req = self._apply()
        with self.assertRaises(ValueError) as ctx:
            approve_leave(self.mgr, req.id)
        self.assertIn('blocked', str(ctx.exception))

    def test_6_6_multi_level_first(self):
        lop = _sl(code='LOP6', name='LOP', credit_method='ON_DEMAND',
                  entitlement_days=0, approval_chain=['REPORTING_MANAGER', 'HR'])
        _pv(lop)
        d = _next_wd()
        req = apply_leave(self.emp, 'LOP6', d, d, 'LOP')
        r = approve_leave(self.mgr, req.id)
        self.assertEqual(r.status, 'PENDING')
        self.assertEqual(r.current_approver, self.hr)

    def test_6_7_multi_level_second(self):
        lop = _sl(code='LOP7', name='LOP', credit_method='ON_DEMAND',
                  entitlement_days=0, approval_chain=['REPORTING_MANAGER', 'HR'])
        _pv(lop)
        d = _next_wd()
        req = apply_leave(self.emp, 'LOP7', d, d, 'LOP')
        approve_leave(self.mgr, req.id)
        req.refresh_from_db()
        r = approve_leave(self.hr, req.id)
        self.assertEqual(r.status, 'APPROVED')

    def test_6_8_hr_flag_SL_over_5(self):
        mon = _next_monday()
        end = mon + timedelta(days=7)
        self.bal.entitled = Decimal('20')
        self.bal.save()
        req = apply_leave(self.emp, 'SL', mon, end, 'long sick')
        approve_leave(self.mgr, req.id)
        self.assertTrue(PendingHRAction.objects.filter(employee=self.emp).exists())

    def test_6_9_lop_payroll_adjustment(self):
        lop = _sl(code='LOP', name='LOP', credit_method='ON_DEMAND',
                  entitlement_days=0, approval_chain=['REPORTING_MANAGER'])
        _pv(lop)
        d = _next_wd()
        req = apply_leave(self.emp, 'LOP', d, d, 'LOP')
        approve_leave(self.mgr, req.id)
        self.assertTrue(PayrollAdjustmentPending.objects.filter(
            employee=self.emp, adjustment_type='LOP_DEDUCTION').exists())

    def test_6_10_approve_already_approved_fails(self):
        req = self._apply()
        approve_leave(self.mgr, req.id)
        with self.assertRaises(ValueError):
            approve_leave(self.mgr, req.id)

    def test_6_11_approve_already_rejected_fails(self):
        req = self._apply()
        reject_leave(self.mgr, req.id, 'no')
        with self.assertRaises(ValueError):
            approve_leave(self.mgr, req.id)

    def test_6_12_idempotency_approve(self):
        req = self._apply()
        approve_leave(self.mgr, req.id, idempotency_key='appr-idem')
        approve_leave(self.mgr, req.id, idempotency_key='appr-idem')
        self.assertEqual(LeaveBalanceLedger.objects.filter(
            employee=self.emp, txn_type='DEBIT_APPROVED').count(), 1)


# ════════════════════════════════════════════════════════════
# Category 7: Balance Manager (10 cases)
# ════════════════════════════════════════════════════════════

class Cat07_BalanceManager(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.emp = _emp('BM-01', dept=self.dept, desg=self.desg)
        self.lt = _sl()

    def test_7_1_credit_bulk(self):
        bal = credit_balance(self.emp, self.lt, 2026, Decimal('8'), 'CREDIT_BULK')
        self.assertEqual(bal.entitled, Decimal('8'))

    def test_7_2_credit_accrual(self):
        bal = credit_balance(self.emp, self.lt, 2026, Decimal('0.5'), 'CREDIT_ACCRUAL')
        self.assertEqual(bal.entitled, Decimal('0.5'))

    def test_7_3_adjust_positive(self):
        _bal(self.emp, self.lt)
        bal = adjust_balance(self.emp, 'BM-01', 'SL', 2, 'bonus')
        self.assertEqual(bal.adjusted, Decimal('2'))
        self.assertTrue(LeaveBalanceLedger.objects.filter(txn_type='CREDIT_ADJUSTMENT').exists())

    def test_7_4_adjust_negative(self):
        _bal(self.emp, self.lt)
        bal = adjust_balance(self.emp, 'BM-01', 'SL', -1, 'correction')
        self.assertEqual(bal.adjusted, Decimal('-1'))
        self.assertTrue(LeaveBalanceLedger.objects.filter(txn_type='DEBIT_ADJUSTMENT').exists())

    def test_7_5_running_balance_sequential(self):
        credit_balance(self.emp, self.lt, 2026, Decimal('8'), 'CREDIT_BULK')
        credit_balance(self.emp, self.lt, 2026, Decimal('2'), 'CREDIT_ADJUSTMENT')
        entries = LeaveBalanceLedger.objects.filter(employee=self.emp).order_by('created_at')
        self.assertEqual(entries[0].running_balance, Decimal('8'))
        self.assertEqual(entries[1].running_balance, Decimal('10'))

    def test_7_6_available_property(self):
        bal = _bal(self.emp, self.lt, entitled=Decimal('8'))
        bal.used = Decimal('3'); bal.pending = Decimal('1')
        bal.carried_forward = Decimal('2'); bal.adjusted = Decimal('1')
        bal.save()
        self.assertEqual(bal.available, Decimal('7'))

    def test_7_7_available_negative(self):
        bal = _bal(self.emp, self.lt, entitled=Decimal('2'))
        bal.pending = Decimal('5'); bal.save()
        self.assertEqual(bal.available, Decimal('-3'))

    def test_7_8_ledger_append_only(self):
        credit_balance(self.emp, self.lt, 2026, Decimal('8'), 'CREDIT_BULK')
        e = LeaveBalanceLedger.objects.first()
        orig = e.days
        credit_balance(self.emp, self.lt, 2026, Decimal('2'), 'CREDIT_ADJUSTMENT')
        self.assertEqual(LeaveBalanceLedger.objects.count(), 2)
        e.refresh_from_db()
        self.assertEqual(e.days, orig)

    def test_7_9_idempotency_adjust(self):
        _bal(self.emp, self.lt)
        adjust_balance(self.emp, 'BM-01', 'SL', 2, 'bonus', idempotency_key='adj-idem')
        adjust_balance(self.emp, 'BM-01', 'SL', 2, 'bonus', idempotency_key='adj-idem')
        self.assertEqual(LeaveBalanceLedger.objects.filter(txn_type='CREDIT_ADJUSTMENT').count(), 1)

    def test_7_10_adjust_reason_logged(self):
        _bal(self.emp, self.lt)
        adjust_balance(self.emp, 'BM-01', 'SL', 2, 'Worked Diwali weekend')
        e = LeaveBalanceLedger.objects.filter(txn_type='CREDIT_ADJUSTMENT').first()
        self.assertIn('Diwali', e.notes)
        self.assertEqual(e.actor, self.emp)


# ════════════════════════════════════════════════════════════
# Category 8: Monthly Accrual (8 cases)
# ════════════════════════════════════════════════════════════

class Cat08_MonthlyAccrual(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.emp = _emp('AC-01', dept=self.dept, desg=self.desg)
        self.pl = _sl(code='PL8', name='PL', credit_method='MONTHLY',
                      monthly_accrual_rate=Decimal('0.5'), entitlement_days=6)
        self.el = _sl(code='EL8', name='EL', credit_method='MONTHLY',
                      monthly_accrual_rate=Decimal('0.5'), entitlement_days=6,
                      year_end_action='CARRY', carry_forward_max=30)
        LeaveBalance.objects.create(employee=self.emp, leave_type=self.pl, year=2026)
        LeaveBalance.objects.create(employee=self.emp, leave_type=self.el, year=2026)

    def test_8_1_PL_accrual(self):
        run_monthly_accrual(date(2026, 5, 1))
        bal = LeaveBalance.objects.get(employee=self.emp, leave_type=self.pl, year=2026)
        self.assertEqual(bal.entitled, Decimal('0.5'))

    def test_8_2_EL_accrual(self):
        run_monthly_accrual(date(2026, 5, 1))
        bal = LeaveBalance.objects.get(employee=self.emp, leave_type=self.el, year=2026)
        self.assertEqual(bal.entitled, Decimal('0.5'))

    def test_8_3_blocked_skipped(self):
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.pl, block_accrual=True,
            effective_from=date(2026, 1, 1), reason='test', created_via='API',
        )
        results = run_monthly_accrual(date(2026, 5, 1))
        self.assertEqual(len([r for r in results if r['type'] == 'PL8' and r['employee'] == 'AC-01']), 0)

    def test_8_4_idempotent(self):
        run_monthly_accrual(date(2026, 5, 1))
        run_monthly_accrual(date(2026, 5, 1))
        self.assertEqual(LeaveBalanceLedger.objects.filter(
            employee=self.emp, leave_type=self.pl, txn_type='CREDIT_ACCRUAL').count(), 1)

    def test_8_5_EL_cap(self):
        bal = LeaveBalance.objects.get(employee=self.emp, leave_type=self.el, year=2026)
        bal.carried_forward = Decimal('30'); bal.save()
        results = run_monthly_accrual(date(2026, 5, 1))
        self.assertEqual(len([r for r in results if r['type'] == 'EL8' and r['employee'] == 'AC-01']), 0)

    def test_8_6_EL_partial(self):
        bal = LeaveBalance.objects.get(employee=self.emp, leave_type=self.el, year=2026)
        bal.carried_forward = Decimal('29.5'); bal.save()
        results = run_monthly_accrual(date(2026, 5, 1))
        el = [r for r in results if r['type'] == 'EL8' and r['employee'] == 'AC-01']
        self.assertEqual(len(el), 1)
        self.assertIn(el[0]['days'], ('0.5', '0.50'))

    def test_8_7_inactive_skipped(self):
        self.emp.is_active = False; self.emp.save()
        results = run_monthly_accrual(date(2026, 5, 1))
        self.assertEqual(len([r for r in results if r['employee'] == 'AC-01']), 0)

    def test_8_8_non_monthly_untouched(self):
        sl = _sl()
        _bal(self.emp, sl)
        results = run_monthly_accrual(date(2026, 5, 1))
        self.assertEqual(len([r for r in results if r['type'] == 'SL']), 0)


# ════════════════════════════════════════════════════════════
# Category 9: Year-End Processing (12 cases)
# ════════════════════════════════════════════════════════════

class Cat09_YearEnd(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.emp = _emp('YE-01', dept=self.dept, desg=self.desg)
        self.sl = _sl(code='SLY', name='SL', year_end_action='LAPSE')
        self.wfh = _sl(code='WFHY', name='WFH', year_end_action='LAPSE')
        self.el = _sl(code='ELY', name='EL', year_end_action='CARRY',
                      carry_forward_max=30, credit_method='MONTHLY',
                      monthly_accrual_rate=Decimal('0.5'))
        self.pl = _sl(code='PLY', name='PL', year_end_action='CONVERT',
                      credit_method='MONTHLY', monthly_accrual_rate=Decimal('0.5'))
        self.pl.convert_to = self.el; self.pl.save()

    def test_9_1_SL_lapses(self):
        b = _bal(self.emp, self.sl, year=2025, entitled=Decimal('8'))
        b.used = Decimal('5'); b.save()
        run_year_end_processing(2025)
        b.refresh_from_db()
        self.assertEqual(b.lapsed, Decimal('3'))

    def test_9_2_WFH_lapses(self):
        b = _bal(self.emp, self.wfh, year=2025, entitled=Decimal('6'))
        b.used = Decimal('4'); b.save()
        run_year_end_processing(2025)
        b.refresh_from_db()
        self.assertEqual(b.lapsed, Decimal('2'))

    def test_9_3_PL_converts_to_EL(self):
        b_pl = _bal(self.emp, self.pl, year=2025, entitled=Decimal('6'))
        b_pl.used = Decimal('2'); b_pl.save()
        _bal(self.emp, self.el, year=2025, entitled=Decimal('0'))
        run_year_end_processing(2025)
        b_el = LeaveBalance.objects.get(employee=self.emp, leave_type=self.el, year=2025)
        self.assertEqual(b_el.converted_in, Decimal('4'))

    def test_9_4_PL_to_EL_cap(self):
        b_pl = _bal(self.emp, self.pl, year=2025, entitled=Decimal('6'))
        b_pl.used = Decimal('2'); b_pl.save()
        _bal(self.emp, self.el, year=2025, entitled=Decimal('28'))
        run_year_end_processing(2025)
        b_el = LeaveBalance.objects.get(employee=self.emp, leave_type=self.el, year=2025)
        self.assertEqual(b_el.converted_in, Decimal('2'))

    def test_9_5_EL_carries(self):
        _bal(self.emp, self.el, year=2025, entitled=Decimal('25'))
        run_year_end_processing(2025)
        new = LeaveBalance.objects.get(employee=self.emp, leave_type=self.el, year=2026)
        self.assertEqual(new.carried_forward, Decimal('25'))

    def test_9_6_EL_carry_capped(self):
        _bal(self.emp, self.el, year=2025, entitled=Decimal('35'))
        run_year_end_processing(2025)
        old = LeaveBalance.objects.get(employee=self.emp, leave_type=self.el, year=2025)
        self.assertEqual(old.lapsed, Decimal('5'))
        new = LeaveBalance.objects.get(employee=self.emp, leave_type=self.el, year=2026)
        self.assertEqual(new.carried_forward, Decimal('30'))

    def test_9_7_bulk_credit_new_year(self):
        _bal(self.emp, self.sl, year=2025, entitled=Decimal('8'))
        run_year_end_processing(2025)
        run_bulk_credit(2026, 'SLY')
        new = LeaveBalance.objects.get(employee=self.emp, leave_type=self.sl, year=2026)
        self.assertEqual(new.entitled, Decimal('8'))

    def test_9_8_pro_rata(self):
        emp2 = _emp('YE-02', dept=self.dept, desg=self.desg,
                     date_of_joining=date(2026, 10, 1))
        run_bulk_credit(2026, 'SLY')
        bal = LeaveBalance.objects.get(employee=emp2, leave_type=self.sl, year=2026)
        self.assertEqual(bal.entitled, Decimal('4.0'))

    def test_9_9_conversion_order(self):
        _bal(self.emp, self.pl, year=2025, entitled=Decimal('4'))
        _bal(self.emp, self.el, year=2025, entitled=Decimal('10'))
        run_year_end_processing(2025)
        new_el = LeaveBalance.objects.get(employee=self.emp, leave_type=self.el, year=2026)
        self.assertEqual(new_el.carried_forward, Decimal('14'))

    def test_9_10_dry_run(self):
        _bal(self.emp, self.sl, year=2025, entitled=Decimal('8'))
        summary = run_year_end_processing(2025, dry_run=True)
        self.assertTrue(len(summary) > 0)
        b = LeaveBalance.objects.get(employee=self.emp, leave_type=self.sl, year=2025)
        self.assertEqual(b.lapsed, Decimal('0'))

    def test_9_11_LOP_no_action(self):
        lop = _sl(code='LOPY', name='LOP', credit_method='ON_DEMAND',
                  entitlement_days=0, year_end_action='LAPSE')
        _bal(self.emp, lop, year=2025, entitled=Decimal('0'))
        summary = run_year_end_processing(2025)
        self.assertEqual(len([s for s in summary if s['type'] == 'LOPY']), 0)

    def test_9_12_event_type_no_action(self):
        bl = _sl(code='BLY', name='BL', credit_method='EVENT',
                 entitlement_days=5, year_end_action='LAPSE')
        summary = run_year_end_processing(2025)
        self.assertEqual(len([s for s in summary if s['type'] == 'BLY']), 0)


# ════════════════════════════════════════════════════════════
# Category 10: Policy Manager (8 cases)
# ════════════════════════════════════════════════════════════

class Cat10_PolicyManager(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.actor = _emp('PM-01', dept=self.dept, desg=self.desg)

    def test_10_1_create(self):
        lt = create_lt_service(self.actor, {
            'code': 'TLT', 'name': 'Test', 'entitlement_days': 5,
            'credit_method': 'BULK', 'approval_chain': ['REPORTING_MANAGER'],
        })
        self.assertTrue(LeavePolicyVersion.objects.filter(leave_type=lt, version=1).exists())

    def test_10_2_update_prospective(self):
        lt = _sl(); _pv(lt)
        update_leave_type(self.actor, 'SL', {'entitlement_days': 10}, 'inc', 'PROSPECTIVE')
        lt.refresh_from_db()
        self.assertEqual(lt.entitlement_days, 10)
        self.assertEqual(LeavePolicyVersion.objects.filter(leave_type=lt).count(), 2)

    def test_10_3_update_retroactive(self):
        lt = _sl(); _pv(lt)
        emp = _emp('PM-E1', dept=self.dept, desg=self.desg)
        _bal(emp, lt, entitled=Decimal('8'))
        update_leave_type(self.actor, 'SL', {'entitlement_days': 10}, 'inc', 'RETROACTIVE')
        lt.refresh_from_db()
        self.assertEqual(lt.entitlement_days, 10)

    def test_10_4_update_version_snapshot(self):
        lt = _sl(); _pv(lt)
        update_leave_type(self.actor, 'SL', {'entitlement_days': 12}, 'Big change', 'PROSPECTIVE')
        v2 = LeavePolicyVersion.objects.filter(leave_type=lt, version=2).first()
        self.assertIn('Big change', v2.change_summary)

    def test_10_5_deactivate(self):
        lt = _sl(code='DA5', name='DA5'); _pv(lt)
        deactivate_leave_type(self.actor, 'DA5')
        lt.refresh_from_db()
        self.assertFalse(lt.is_active)

    def test_10_6_deactivated_blocks_new(self):
        lt = _sl(code='DA6', name='DA6'); _pv(lt)
        mgr = _emp('PM-M6', dept=self.dept, desg=self.desg)
        emp = _emp('PM-E6', dept=self.dept, desg=self.desg, reporting_manager=mgr)
        _bal(emp, lt)
        deactivate_leave_type(self.actor, 'DA6')
        with self.assertRaises(ValueError):
            apply_leave(emp, 'DA6', _next_wd(), _next_wd(), 'test')

    @patch('leaves.services.policy_manager.signals')
    def test_10_7_notification(self, mock_signals):
        lt = _sl(code='NT7', name='NT7'); _pv(lt)
        update_leave_type(self.actor, 'NT7', {'entitlement_days': 12}, 'inc', 'PROSPECTIVE')
        mock_signals.policy_changed.send.assert_called()

    def test_10_8_version_history(self):
        lt = _sl(code='VH8', name='VH8'); _pv(lt)
        update_leave_type(self.actor, 'VH8', {'entitlement_days': 10}, 'v2', 'PROSPECTIVE')
        update_leave_type(self.actor, 'VH8', {'entitlement_days': 12}, 'v3', 'PROSPECTIVE')
        vs = LeavePolicyVersion.objects.filter(leave_type=lt).order_by('version')
        self.assertEqual(vs.count(), 3)
        self.assertEqual(vs[0].version, 1)
        self.assertEqual(vs[2].version, 3)


# ════════════════════════════════════════════════════════════
# Category 11: Override Manager (10 cases)
# ════════════════════════════════════════════════════════════

class Cat11_OverrideManager(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.actor = _emp('OM-A', dept=self.dept, desg=self.desg)
        self.emp = _emp('OM-01', dept=self.dept, desg=self.desg)
        self.lt = _sl()

    def test_11_1_create(self):
        o = create_override(self.actor, 'OM-01', 'SL', block_accrual=True,
                            effective_from=date(2026, 5, 1), effective_to=date(2026, 5, 31),
                            reason='PIP')
        self.assertTrue(o.is_active)

    def test_11_2_conflict(self):
        create_override(self.actor, 'OM-01', 'SL', block_accrual=True,
                        effective_from=date(2026, 5, 1), effective_to=date(2026, 5, 31), reason='1')
        with self.assertRaises(ValueError):
            create_override(self.actor, 'OM-01', 'SL', block_application=True,
                            effective_from=date(2026, 5, 15), effective_to=date(2026, 6, 15), reason='2')

    def test_11_3_remove(self):
        o = create_override(self.actor, 'OM-01', 'SL', block_accrual=True,
                            effective_from=date.today(), reason='temp')
        remove_override(self.actor, o.id, 'done')
        self.assertFalse(EmployeeOverride.objects.get(pk=o.pk).is_active)
        self.assertFalse(get_effective_config(self.emp, self.lt)['block_accrual'])

    def test_11_4_null_type_all(self):
        create_override(self.actor, 'OM-01', None, block_application=True,
                        effective_from=date.today(), reason='freeze')
        lt2 = _sl(code='PL11', name='PL')
        self.assertTrue(get_effective_config(self.emp, self.lt)['block_application'])
        self.assertTrue(get_effective_config(self.emp, lt2)['block_application'])

    def test_11_5_expired(self):
        create_override(self.actor, 'OM-01', 'SL', block_application=True,
                        effective_from=date.today() - timedelta(days=10),
                        effective_to=date.today() - timedelta(days=1), reason='old')
        self.assertFalse(get_effective_config(self.emp, self.lt)['block_application'])

    def test_11_6_permanent(self):
        create_override(self.actor, 'OM-01', 'SL', block_application=True,
                        effective_from=date.today() - timedelta(days=30),
                        effective_to=None, reason='perm')
        self.assertTrue(get_effective_config(self.emp, self.lt)['block_application'])

    def test_11_7_waive_merges(self):
        wfh = _sl(code='WFH11', name='WFH', probation_eligible=False)
        create_override(self.actor, 'OM-01', 'WFH11',
                        waive_restriction={'probation_eligible': True},
                        effective_from=date.today(), reason='med')
        self.assertTrue(get_effective_config(self.emp, wfh)['probation_eligible'])

    def test_11_8_no_leak(self):
        emp2 = _emp('OM-02', dept=self.dept, desg=self.desg)
        create_override(self.actor, 'OM-01', 'SL', block_application=True,
                        effective_from=date.today(), reason='specific')
        self.assertTrue(get_effective_config(self.emp, self.lt)['block_application'])
        self.assertFalse(get_effective_config(emp2, self.lt)['block_application'])

    def test_11_9_batch(self):
        for i in range(5):
            _emp(f'BO-{i}', dept=self.dept, desg=self.desg, probation_status='ON_PROBATION')
        b = bulk_create_overrides(self.actor, {'is_on_probation': True},
                                  {'leave_type_code': 'SL', 'block_accrual': True,
                                   'effective_from': str(date.today()), 'reason': 'batch'})
        self.assertEqual(b.status, 'PENDING_CONFIRMATION')
        self.assertEqual(b.affected_count, 5)

    def test_11_10_rollback(self):
        for i in range(3):
            _emp(f'RB-{i}', dept=self.dept, desg=self.desg, probation_status='ON_PROBATION')
        b = bulk_create_overrides(self.actor, {'is_on_probation': True},
                                  {'leave_type_code': 'SL', 'block_accrual': True,
                                   'effective_from': str(date.today()), 'reason': 'batch'})
        confirm_batch(self.actor, b.id)
        self.assertEqual(EmployeeOverride.objects.filter(batch_id=b, is_active=True).count(), 3)
        rollback_batch(self.actor, b.id, 'undo')
        self.assertEqual(EmployeeOverride.objects.filter(batch_id=b, is_active=True).count(), 0)


# ════════════════════════════════════════════════════════════
# Category 12: Approver Resolution (8 cases)
# ════════════════════════════════════════════════════════════

class Cat12_ApproverResolution(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.hr_dept = _dept('HRA', 'HR')
        self.desg = _desg()
        self.hr = _emp('HR-12', 'Bhavishya', dept=self.hr_dept, desg=_hr_desg())
        self.ceo = _emp('CEO-12', 'Saiteja', dept=self.dept, desg=_ceo_desg(), reporting_manager=None)
        self.mgr = _emp('MGR-12', 'Chandrakala', dept=self.dept, desg=self.desg,
                        reporting_manager=self.ceo)
        self.emp = _emp('E-12', 'Prithvi', dept=self.dept, desg=self.desg,
                        reporting_manager=self.mgr)
        self.lt = _sl()

    def test_12_1_normal_gets_manager(self):
        self.assertEqual(determine_approver(self.emp, self.lt, _config()), self.mgr)

    def test_12_2_manager_on_leave_fallback(self):
        fb = _emp('FB-12', 'Dinesh', dept=self.dept, desg=self.desg)
        LeaveRequest.objects.create(
            employee=self.mgr, leave_type=self.lt,
            start_date=date.today(), end_date=date.today() + timedelta(days=5),
            duration_days=5, reason='vac', status='APPROVED',
        )
        FallbackManager.objects.create(
            employee=self.emp, primary_manager=self.mgr, fallback_manager=fb,
            effective_from=date.today(), is_active=True,
        )
        self.assertEqual(determine_approver(self.emp, self.lt, _config()), fb)

    def test_12_3_manager_on_leave_no_fallback_hr(self):
        LeaveRequest.objects.create(
            employee=self.mgr, leave_type=self.lt,
            start_date=date.today(), end_date=date.today() + timedelta(days=5),
            duration_days=5, reason='vac', status='APPROVED',
        )
        self.assertEqual(determine_approver(self.emp, self.lt, _config()), self.hr)

    def test_12_4_ceo_self(self):
        self.assertEqual(determine_approver(self.ceo, self.lt, _config()), self.ceo)

    def test_12_5_hr_escalation(self):
        config = CompanyConfig.get()
        config.top_level_approval_mode = 'ESCALATE_TO_CEO'
        config.save()
        self.assertEqual(determine_approver(self.hr, self.lt, _config()), self.ceo)

    def test_12_6_null_manager(self):
        lone = _emp('LONE-12', dept=self.dept, desg=self.desg, reporting_manager=None)
        self.assertEqual(determine_approver(lone, self.lt, _config()), lone)

    def test_12_7_expired_fallback(self):
        fb = _emp('FBE-12', dept=self.dept, desg=self.desg)
        LeaveRequest.objects.create(
            employee=self.mgr, leave_type=self.lt,
            start_date=date.today(), end_date=date.today() + timedelta(days=5),
            duration_days=5, reason='vac', status='APPROVED',
        )
        FallbackManager.objects.create(
            employee=self.emp, primary_manager=self.mgr, fallback_manager=fb,
            effective_from=date.today() - timedelta(days=30),
            effective_to=date.today() - timedelta(days=1), is_active=True,
        )
        self.assertEqual(determine_approver(self.emp, self.lt, _config()), self.hr)

    def test_12_8_custom_chain_HR(self):
        self.assertEqual(determine_approver(self.emp, self.lt, _config(approval_chain=['HR'])), self.hr)


# ════════════════════════════════════════════════════════════
# Category 13: Batch Operations (6 cases)
# ════════════════════════════════════════════════════════════

class Cat13_BatchOperations(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.actor = _emp('BA-A', dept=self.dept, desg=self.desg)
        self.lt = _sl()
        for i in range(5):
            _emp(f'BA-{i}', dept=self.dept, desg=self.desg, probation_status='ON_PROBATION')

    def _batch(self):
        return bulk_create_overrides(self.actor, {'is_on_probation': True},
                                     {'leave_type_code': 'SL', 'block_accrual': True,
                                      'effective_from': str(date.today()), 'reason': 'batch'})

    def test_13_1_preview(self):
        b = self._batch()
        self.assertEqual(b.status, 'PENDING_CONFIRMATION')
        self.assertEqual(len(b.affected_employees), 5)

    def test_13_2_confirm(self):
        b = self._batch()
        confirm_batch(self.actor, b.id)
        b.refresh_from_db()
        self.assertEqual(b.status, 'EXECUTED')
        self.assertEqual(EmployeeOverride.objects.filter(batch_id=b).count(), 5)

    def test_13_3_confirm_already_executed_fails(self):
        b = self._batch()
        confirm_batch(self.actor, b.id)
        with self.assertRaises(ValueError):
            confirm_batch(self.actor, b.id)

    def test_13_4_rollback(self):
        b = self._batch()
        confirm_batch(self.actor, b.id)
        rollback_batch(self.actor, b.id, 'undo')
        b.refresh_from_db()
        self.assertEqual(b.status, 'ROLLED_BACK')
        self.assertEqual(EmployeeOverride.objects.filter(batch_id=b, is_active=True).count(), 0)

    def test_13_5_double_confirm_fails(self):
        b = self._batch()
        confirm_batch(self.actor, b.id)
        with self.assertRaises(ValueError):
            confirm_batch(self.actor, b.id)

    def test_13_6_filter_dept(self):
        dept2 = _dept('MKT2', 'Mkt')
        _emp('BA-MKT', dept=dept2, desg=self.desg, probation_status='ON_PROBATION')
        b = bulk_create_overrides(self.actor, {'department': 'ENG', 'is_on_probation': True},
                                  {'block_accrual': True, 'effective_from': str(date.today()), 'reason': 'eng'})
        eng_count = Employee.objects.filter(
            department__code='ENG', probation_status='ON_PROBATION', is_active=True).count()
        self.assertEqual(b.affected_count, eng_count)


# ════════════════════════════════════════════════════════════
# Category 14: PendingHRAction Nudges (8 cases)
# ════════════════════════════════════════════════════════════

class Cat14_HRNudges(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.hr = _emp('HR-14', dept=self.dept, desg=self.desg)

    def test_14_1_dept_transfer_nudge(self):
        emp, _ = add_employee(employee_id='N-01', first_name='N', email='n01@t.co',
                              gender='M', department=self.dept, designation=self.desg,
                              date_of_joining=date(2024, 1, 1))
        EmployeeOverride.objects.create(employee=emp, leave_type=None, block_accrual=True,
                                        effective_from=date.today(), reason='old', created_via='API')
        dept2 = _dept('TR14', 'TR')
        transfer_employee(self.hr, 'N-01', department=dept2)
        self.assertTrue(PendingHRAction.objects.filter(employee=emp, trigger_type='DEPARTMENT_CHANGE').exists())

    def test_14_2_confirmation_nudge(self):
        emp, _ = add_employee(employee_id='N-02', first_name='N', email='n02@t.co',
                              gender='M', department=self.dept, designation=self.desg,
                              date_of_joining=date(2024, 1, 1), probation_status='ON_PROBATION')
        confirm_employee(self.hr, 'N-02')
        self.assertTrue(PendingHRAction.objects.filter(employee=emp, trigger_type='CONFIRMATION').exists())

    def test_14_3_exit_high_priority(self):
        emp, _ = add_employee(employee_id='N-03', first_name='N', email='n03@t.co',
                              gender='M', department=self.dept, designation=self.desg,
                              date_of_joining=date(2024, 1, 1))
        deactivate_employee(self.hr, 'N-03', date.today(), 'RESIGNED')
        n = PendingHRAction.objects.filter(employee=emp, trigger_type='EXIT').first()
        self.assertIsNotNone(n)
        self.assertEqual(n.priority, 'HIGH')

    def test_14_4_manager_change_log(self):
        mgr1 = _emp('NM-01', dept=self.dept, desg=self.desg)
        mgr2 = _emp('NM-02', dept=self.dept, desg=self.desg)
        emp, _ = add_employee(employee_id='N-04', first_name='N', email='n04@t.co',
                              gender='M', department=self.dept, designation=self.desg,
                              date_of_joining=date(2024, 1, 1), reporting_manager=mgr1)
        transfer_employee(self.hr, 'N-04', reporting_manager=mgr2)
        self.assertTrue(EmployeeChangeLog.objects.filter(employee=emp, field_changed='reporting_manager').exists())

    def test_14_5_resolve(self):
        n = create_nudge('CONFIRMATION', self.hr, 'test', 'desc')
        r = resolve_action(self.hr, n.id, 'RESOLVED', 'done')
        self.assertEqual(r.status, 'RESOLVED')
        self.assertEqual(r.resolved_by, self.hr)

    def test_14_6_dismiss(self):
        n = create_nudge('CONFIRMATION', self.hr, 'test', 'desc')
        r = resolve_action(self.hr, n.id, 'DISMISSED', 'nope')
        self.assertEqual(r.status, 'DISMISSED')

    def test_14_7_execute_remove_override(self):
        emp = _emp('N-07', dept=self.dept, desg=self.desg)
        lt = _sl(code='SLN7', name='SLN7')
        o = EmployeeOverride.objects.create(employee=emp, leave_type=lt, block_accrual=True,
                                            effective_from=date.today(), reason='old', created_via='API')
        n = create_nudge('CONFIRMATION', emp, 'test', 'desc',
                         suggested_actions=[{'action': 'remove_override', 'override_id': o.id}])
        execute_suggested_action(self.hr, n.id, 0)
        o.refresh_from_db()
        self.assertFalse(o.is_active)

    def test_14_8_manager_on_leave_nudge(self):
        mgr = _emp('NML-01', dept=self.dept, desg=self.desg)
        create_nudge('MANAGER_ON_LEAVE', mgr, f'{mgr.full_name} on leave',
                      'Reroute', priority='HIGH')
        n = PendingHRAction.objects.filter(trigger_type='MANAGER_ON_LEAVE').first()
        self.assertEqual(n.priority, 'HIGH')


# ════════════════════════════════════════════════════════════
# Category 15: Idempotency (6 cases)
# ════════════════════════════════════════════════════════════

class Cat15_Idempotency(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.mgr = _emp('IM-M', dept=self.dept, desg=self.desg)
        self.emp = _emp('IM-01', dept=self.dept, desg=self.desg, reporting_manager=self.mgr)
        self.lt = _sl(); _pv(self.lt)
        self.bal = _bal(self.emp, self.lt)

    def test_15_1_apply_idempotent(self):
        d = _next_wd()
        apply_leave(self.emp, 'SL', d, d, 'test', idempotency_key='i151')
        apply_leave(self.emp, 'SL', d, d, 'test', idempotency_key='i151')
        self.assertEqual(LeaveRequest.objects.filter(employee=self.emp).count(), 1)

    def test_15_2_approve_idempotent(self):
        d = _next_wd()
        req = apply_leave(self.emp, 'SL', d, d, 'test')
        approve_leave(self.mgr, req.id, idempotency_key='i152')
        approve_leave(self.mgr, req.id, idempotency_key='i152')
        self.assertEqual(LeaveBalanceLedger.objects.filter(txn_type='DEBIT_APPROVED').count(), 1)

    def test_15_3_adjust_idempotent(self):
        adjust_balance(self.emp, 'IM-01', 'SL', 2, 'bonus', idempotency_key='i153')
        adjust_balance(self.emp, 'IM-01', 'SL', 2, 'bonus', idempotency_key='i153')
        self.assertEqual(LeaveBalanceLedger.objects.filter(txn_type='CREDIT_ADJUSTMENT').count(), 1)

    def test_15_4_generic_idempotent(self):
        counter = [0]
        def _fn():
            counter[0] += 1
            return {'ok': True}
        execute_with_idempotency('i154', 'test', {}, _fn)
        execute_with_idempotency('i154', 'test', {}, _fn)
        self.assertEqual(counter[0], 1)

    def test_15_5_different_keys_separate(self):
        d = _next_wd(); d2 = _next_wd(5)
        apply_leave(self.emp, 'SL', d, d, 't1', idempotency_key='i155a')
        apply_leave(self.emp, 'SL', d2, d2, 't2', idempotency_key='i155b')
        self.assertEqual(LeaveRequest.objects.filter(employee=self.emp).count(), 2)

    def test_15_6_failed_cached(self):
        counter = [0]
        def _fn():
            counter[0] += 1
            raise ValueError("boom")
        with self.assertRaises(ValueError):
            execute_with_idempotency('i156', 'test', {}, _fn)
        result = execute_with_idempotency('i156', 'test', {}, _fn)
        self.assertEqual(counter[0], 1)
        self.assertIn('error', result)


# ════════════════════════════════════════════════════════════
# Category 16: Edge Cases (12 cases)
# ════════════════════════════════════════════════════════════

class Cat16_EdgeCases(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.hr_dept = _dept('HRE', 'HR')
        self.desg = _desg()
        self.hr = _emp('HR-16', dept=self.hr_dept, desg=_hr_desg())
        self.ceo = _emp('CEO-16', dept=self.dept, desg=_ceo_desg(), reporting_manager=None)
        self.mgr = _emp('MGR-16', dept=self.dept, desg=self.desg, reporting_manager=self.ceo)
        self.emp = _emp('EC-01', dept=self.dept, desg=self.desg, reporting_manager=self.mgr)
        self.lt = _sl(); _pv(self.lt)
        self.bal = _bal(self.emp, self.lt)

    def test_16_1_overlapping_overrides(self):
        create_override(self.hr, 'EC-01', 'SL', block_accrual=True,
                        effective_from=date(2026, 5, 1), effective_to=date(2026, 5, 31), reason='1')
        with self.assertRaises(ValueError):
            create_override(self.hr, 'EC-01', 'SL', block_application=True,
                            effective_from=date(2026, 5, 15), effective_to=date(2026, 6, 15), reason='2')

    def test_16_2_retroactive_policy(self):
        update_leave_type(self.hr, 'SL', {'entitlement_days': 10}, 'inc', 'RETROACTIVE')
        self.lt.refresh_from_db()
        self.assertEqual(self.lt.entitlement_days, 10)

    def test_16_3_policy_version_at_approval(self):
        d = _next_wd()
        req = apply_leave(self.emp, 'SL', d, d, 'test')
        self.assertEqual(req.policy_version.version, 1)
        update_leave_type(self.hr, 'SL', {'entitlement_days': 12}, 'up', 'PROSPECTIVE')
        r = approve_leave(self.mgr, req.id)
        self.assertEqual(r.status, 'APPROVED')

    def test_16_4_AM_PM_coexist(self):
        d = _next_wd()
        apply_leave(self.emp, 'SL', d, d, 'AM', is_half_day=True, half_day_period='AM')
        lt2 = _sl(code='WFH16', name='WFH'); _pv(lt2); _bal(self.emp, lt2)
        req2 = apply_leave(self.emp, 'WFH16', d, d, 'PM', is_half_day=True, half_day_period='PM')
        self.assertEqual(req2.status, 'PENDING')

    def test_16_5_ceo_self(self):
        _bal(self.ceo, self.lt)
        d = _next_wd()
        req = apply_leave(self.ceo, 'SL', d, d, 'test')
        r = approve_leave(self.ceo, req.id)
        self.assertEqual(r.status, 'APPROVED')

    def test_16_6_override_expiry_boundary(self):
        EmployeeOverride.objects.create(employee=self.emp, leave_type=self.lt,
                                        block_accrual=True, effective_from=date(2026, 5, 1),
                                        effective_to=date(2026, 5, 31), reason='may', created_via='API')
        self.assertTrue(get_effective_config(self.emp, self.lt, date(2026, 5, 15))['block_accrual'])
        self.assertFalse(get_effective_config(self.emp, self.lt, date(2026, 6, 1))['block_accrual'])

    def test_16_7_lop_payroll(self):
        lop = _sl(code='LOP', name='LOP', credit_method='ON_DEMAND',
                  entitlement_days=0, approval_chain=['REPORTING_MANAGER']); _pv(lop)
        d = _next_wd()
        req = apply_leave(self.emp, 'LOP', d, d, 'LOP')
        approve_leave(self.mgr, req.id)
        self.assertTrue(PayrollAdjustmentPending.objects.filter(employee=self.emp).exists())

    def test_16_8_retry_no_duplicate(self):
        d = _next_wd()
        apply_leave(self.emp, 'SL', d, d, 'test', idempotency_key='r168')
        apply_leave(self.emp, 'SL', d, d, 'test', idempotency_key='r168')
        self.assertEqual(LeaveRequest.objects.filter(employee=self.emp).count(), 1)

    def test_16_9_granularity(self):
        EmployeeOverride.objects.create(employee=self.emp, leave_type=self.lt,
                                        block_accrual=True, block_application=False,
                                        effective_from=date.today(), reason='g', created_via='API')
        c = get_effective_config(self.emp, self.lt)
        self.assertTrue(c['block_accrual'])
        self.assertFalse(c['block_application'])
        d = _next_wd()
        req = apply_leave(self.emp, 'SL', d, d, 'test')
        self.assertEqual(req.status, 'PENDING')

    def test_16_10_batch_atomic(self):
        for i in range(5):
            _emp(f'BAT-{i}', dept=self.dept, desg=self.desg, probation_status='ON_PROBATION')
        b = bulk_create_overrides(self.hr, {'is_on_probation': True},
                                  {'leave_type_code': 'SL', 'block_accrual': True,
                                   'effective_from': str(date.today()), 'reason': 'b'})
        confirm_batch(self.hr, b.id)
        self.assertEqual(EmployeeOverride.objects.filter(batch_id=b).count(), 5)

    def test_16_11_audit_attribution(self):
        adjust_balance(self.hr, 'EC-01', 'SL', 2, 'audit')
        e = LeaveBalanceLedger.objects.filter(txn_type='CREDIT_ADJUSTMENT').last()
        self.assertEqual(e.actor, self.hr)
        self.assertEqual(e.actor_channel, 'AGENT')

    @patch('leaves.services.leave_approval.signals')
    def test_16_12_signal_on_approval(self, mock_signals):
        d = _next_wd()
        req = apply_leave(self.emp, 'SL', d, d, 'test')
        approve_leave(self.mgr, req.id)
        mock_signals.leave_approved.send.assert_called_once()


# ════════════════════════════════════════════════════════════
# Category 17: MCP Tool Wiring (8 cases)
# ════════════════════════════════════════════════════════════

class Cat17_MCPToolWiring(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept()
        self.desg = _desg()
        self.emp = _emp('MCP-01', dept=self.dept, desg=self.desg)
        self.lt = _sl(); _pv(self.lt); _bal(self.emp, self.lt)

    def test_17_1_all_tools(self):
        from mcp_server.registry import ALL_TOOLS
        self.assertEqual(len(ALL_TOOLS), 48)

    def test_17_2_employee_8(self):
        from mcp_server.registry import get_tools_for_role
        self.assertEqual(len(get_tools_for_role('EMPLOYEE')), 8)

    def test_17_3_manager_14(self):
        from mcp_server.registry import get_tools_for_role
        self.assertEqual(len(get_tools_for_role('MANAGER')), 14)

    def test_17_4_admin_48(self):
        from mcp_server.registry import get_tools_for_role
        self.assertEqual(len(get_tools_for_role('ADMIN')), 48)

    def test_17_5_execute_routes(self):
        from mcp_server.executor import execute_tool
        result = execute_tool('search_employees', {}, {'employee_id': 'MCP-01'})
        self.assertNotIn('error', result)

    def test_17_6_unknown_tool(self):
        from mcp_server.executor import execute_tool
        result = execute_tool('nonexistent', {}, {'employee_id': 'MCP-01'})
        self.assertIn('error', result)

    def test_17_7_role_schemas(self):
        from mcp_server.registry import list_tool_schemas
        self.assertTrue(len(list_tool_schemas('ADMIN')) > len(list_tool_schemas('EMPLOYEE')))

    def test_17_8_schema_fields(self):
        from mcp_server.registry import ALL_TOOLS
        for t in ALL_TOOLS:
            self.assertIn('name', t)
            self.assertIn('description', t)
            self.assertIn('input_schema', t)
            self.assertIn('handler', t)


# ════════════════════════════════════════════════════════════
# Category 18: Chatbot Integration (10 cases)
# Tool execution pipeline without actual OpenAI calls
# ════════════════════════════════════════════════════════════

class Cat18_ChatbotIntegration(TestCase):
    def setUp(self):
        _setup_company_config()
        self.dept = _dept('ENGC', 'Engineering')
        self.hr_dept = _dept('HRC', 'HR')
        self.desg = _desg('SE Chatbot', 3)
        self.mgr = _emp('CMGR-01', 'Chandrakala', dept=self.dept, desg=self.desg)
        self.emp = _emp('CEMP-01', 'Prithvi', 'P', dept=self.dept, desg=self.desg,
                        reporting_manager=self.mgr)
        self.hr = _emp('CHR-01', 'Bhavishya', dept=self.hr_dept, desg=_hr_desg())
        self.lt = _sl(); _pv(self.lt)
        _bal(self.emp, self.lt); _bal(self.mgr, self.lt)

    def _exec(self, tool, args, eid, role='EMPLOYEE'):
        from mcp_server.executor import execute_tool
        return execute_tool(tool, args, {'employee_id': eid, 'role': role})

    def test_18_1_balance(self):
        r = self._exec('get_my_balance', {}, 'CEMP-01')
        self.assertNotIn('error', r)

    def test_18_2_apply_sl(self):
        d = _next_wd()
        r = self._exec('apply_leave', {
            'leave_type': 'SL', 'start_date': str(d), 'end_date': str(d), 'reason': 'Sick',
        }, 'CEMP-01')
        self.assertNotIn('error', r)
        self.assertTrue(LeaveRequest.objects.filter(employee=self.emp).exists())

    def test_18_3_policy(self):
        r = self._exec('get_leave_policy', {}, 'CEMP-01')
        self.assertNotIn('error', r)

    def test_18_4_manager_pending(self):
        d = _next_wd()
        apply_leave(self.emp, 'SL', d, d, 'sick')
        r = self._exec('get_team_requests', {'status': 'PENDING'}, 'CMGR-01', 'MANAGER')
        self.assertNotIn('error', r)

    def test_18_5_manager_approve(self):
        d = _next_wd()
        req = apply_leave(self.emp, 'SL', d, d, 'sick')
        r = self._exec('approve_leave', {'request_id': req.id, 'remarks': 'OK'}, 'CMGR-01', 'MANAGER')
        self.assertNotIn('error', r)
        req.refresh_from_db()
        self.assertEqual(req.status, 'APPROVED')

    def test_18_6_hr_balance(self):
        r = self._exec('get_my_balance', {}, 'CEMP-01', 'ADMIN')
        self.assertNotIn('error', r)

    def test_18_7_hr_override(self):
        r = self._exec('create_override', {
            'employee_id': 'CEMP-01', 'leave_type_code': 'SL',
            'block_application': True, 'effective_from': str(date(2026, 5, 1)),
            'effective_to': str(date(2026, 5, 31)), 'reason': 'PIP',
        }, 'CHR-01', 'ADMIN')
        self.assertNotIn('error', r)
        self.assertTrue(EmployeeOverride.objects.filter(employee=self.emp).exists())

    def test_18_8_hr_update_policy(self):
        r = self._exec('update_leave_type', {
            'code': 'SL', 'changes': {'entitlement_days': 10}, 'change_summary': 'Inc to 10',
        }, 'CHR-01', 'ADMIN')
        self.assertNotIn('error', r)
        self.lt.refresh_from_db()
        self.assertEqual(self.lt.entitlement_days, 10)

    def test_18_9_hr_bulk_credit(self):
        r = self._exec('trigger_bulk_credit', {'year': 2026}, 'CHR-01', 'ADMIN')
        self.assertNotIn('error', r)

    def test_18_10_employee_policy(self):
        r = self._exec('get_leave_policy', {}, 'CEMP-01')
        self.assertNotIn('error', r)
