"""
Comprehensive tests for all 48 MCP tools in the HRMS leave management system.

Tests are executed via `execute_tool()` from mcp_server/executor.py, which
handles argument remapping, employee context injection, and result serialization.

Organized into test classes:
  - TestParameterMapping: verify _ARG_REMAP for every remapped tool
  - TestEmployeeGetBalance: get_my_balance
  - TestEmployeeGetRequests: get_my_requests
  - TestValidateLeave: all validation rules
  - TestApplyLeave: application, balance hold, idempotency
  - TestCancelLeave: pending, approved, ownership
  - TestGetLeavePolicy: policy listing
  - TestOptionalHolidays: employee + admin holiday tools
  - TestManagerApproval: approve/reject flow, wrong approver
  - TestManagerTeamTools: team requests, balance, calendar
  - TestAdminLeaveTypeTools: create, update, deactivate
  - TestAdminOverrideTools: create, remove, get overrides
  - TestAdminBalanceAdjust: positive/negative adjustments
  - TestAdminEmployeeMgmt: add, update, confirm, deactivate, transfer, get, search
  - TestAdminOrgTools: departments, teams, membership
  - TestAdminAccrualTools: bulk credit, monthly accrual, year end
  - TestAdminHRActions: pending actions, resolve, execute suggestion
  - TestAdminBatchTools: bulk create, confirm, rollback
  - TestAdminFallbackTools: set fallback manager
  - TestResponseFormat: serialization correctness
  - TestErrorHandling: unknown tool, invalid employee, handler errors
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from django.test import TestCase

from employees.models import Department, Designation, Employee, Team, PendingHRAction
from leaves.models import (
    LeaveType, LeaveBalance, LeaveBalanceLedger, LeaveRequest,
    LeavePolicyVersion, CompanyConfig, EmployeeOverride,
    OptionalHoliday, OptionalHolidaySelection, BatchOperation,
    FallbackManager, IdempotencyLog,
)
from mcp_server.executor import execute_tool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _next_weekday(days_ahead=1):
    """Return a date `days_ahead` from today that falls on a weekday."""
    d = date.today() + timedelta(days=days_ahead)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _prev_weekday(days_back=1):
    """Return a date `days_back` before today that falls on a weekday."""
    d = date.today() - timedelta(days=days_back)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _setup_base():
    """Create minimal shared fixtures: company config, dept, designation, manager, employee."""
    CompanyConfig.objects.get_or_create(pk=1, defaults={
        'leave_year_start_month': 4,
        'weekend_days': [5, 6],
        'working_days_per_week': 5,
    })
    dept = Department.objects.create(code='ENG', name='Engineering')
    desg = Designation.objects.create(title='Software Engineer', level=3)
    mgr_desg = Designation.objects.create(title='Sr. Project Manager', level=6)
    hr_desg = Designation.objects.create(title='Senior HR Manager', level=7)
    hr_dept = Department.objects.create(code='HR', name='Human Resources')

    manager = Employee.objects.create(
        employee_id='MGR-001', first_name='Manager', last_name='One',
        email='mgr001@test.co', gender='F', department=dept, designation=mgr_desg,
        date_of_joining=date(2020, 1, 1), probation_status='CONFIRMED',
    )
    employee = Employee.objects.create(
        employee_id='EMP-001', first_name='Alice', last_name='Dev',
        email='emp001@test.co', gender='M', department=dept, designation=desg,
        date_of_joining=date(2024, 1, 1), probation_status='CONFIRMED',
        reporting_manager=manager,
    )
    hr_admin = Employee.objects.create(
        employee_id='HR-001', first_name='HR', last_name='Admin',
        email='hr001@test.co', gender='F', department=hr_dept, designation=hr_desg,
        date_of_joining=date(2020, 1, 1), probation_status='CONFIRMED',
    )
    return dept, desg, manager, employee, hr_admin


def _make_sl(**overrides):
    """Create a Sick Leave type with sensible defaults."""
    defaults = dict(
        code='SL', name='Sick Leave', entitlement_days=8, credit_method='BULK',
        approval_chain=['REPORTING_MANAGER'], half_day_allowed=True,
        can_apply_in_advance=False, can_apply_retroactively=True,
        document_required=True, document_required_after_days=2,
        probation_eligible=True, is_pro_rata=True,
        year_end_action='LAPSE',
    )
    defaults.update(overrides)
    lt = LeaveType.objects.create(**defaults)
    LeavePolicyVersion.objects.create(
        leave_type=lt, version=1, snapshot={}, change_summary='init', changed_via='API',
    )
    return lt


def _make_pl(**overrides):
    """Create a Planned Leave (PL) type."""
    defaults = dict(
        code='PL', name='Planned Leave', entitlement_days=12, credit_method='MONTHLY',
        monthly_accrual_rate=Decimal('1.0'),
        approval_chain=['REPORTING_MANAGER'], half_day_allowed=True,
        advance_notice_days=2, can_apply_in_advance=True,
        can_apply_retroactively=False, probation_eligible=True,
        year_end_action='CONVERT',
    )
    defaults.update(overrides)
    lt = LeaveType.objects.create(**defaults)
    LeavePolicyVersion.objects.create(
        leave_type=lt, version=1, snapshot={}, change_summary='init', changed_via='API',
    )
    return lt


def _make_el(**overrides):
    """Create an Earned Leave (EL) type."""
    defaults = dict(
        code='EL', name='Earned Leave', entitlement_days=15, credit_method='MONTHLY',
        monthly_accrual_rate=Decimal('1.25'),
        approval_chain=['REPORTING_MANAGER'], half_day_allowed=True,
        advance_notice_days=3, can_apply_in_advance=True,
        can_apply_retroactively=False, probation_eligible=True,
        year_end_action='CARRY', carry_forward_max=15,
    )
    defaults.update(overrides)
    lt = LeaveType.objects.create(**defaults)
    LeavePolicyVersion.objects.create(
        leave_type=lt, version=1, snapshot={}, change_summary='init', changed_via='API',
    )
    return lt


def _make_wfh(**overrides):
    """Create a WFH leave type."""
    defaults = dict(
        code='WFH', name='Work From Home', entitlement_days=12, credit_method='BULK',
        approval_chain=['REPORTING_MANAGER'], half_day_allowed=False,
        advance_notice_days=1, can_apply_in_advance=True,
        can_apply_retroactively=False, probation_eligible=False,
        consecutive_day_restriction=True,
        year_end_action='LAPSE',
    )
    defaults.update(overrides)
    lt = LeaveType.objects.create(**defaults)
    LeavePolicyVersion.objects.create(
        leave_type=lt, version=1, snapshot={}, change_summary='init', changed_via='API',
    )
    return lt


def _make_lop(**overrides):
    """Create a Loss of Pay (LOP) type."""
    defaults = dict(
        code='LOP', name='Loss of Pay', entitlement_days=0, credit_method='ON_DEMAND',
        approval_chain=['REPORTING_MANAGER', 'HR'], half_day_allowed=True,
        can_apply_in_advance=True, can_apply_retroactively=True,
        probation_eligible=True,
        year_end_action='LAPSE',
    )
    defaults.update(overrides)
    lt = LeaveType.objects.create(**defaults)
    LeavePolicyVersion.objects.create(
        leave_type=lt, version=1, snapshot={}, change_summary='init', changed_via='API',
    )
    return lt


def _make_ml(**overrides):
    """Create a Maternity Leave type."""
    defaults = dict(
        code='ML', name='Maternity Leave', entitlement_days=182, credit_method='EVENT',
        approval_chain=['REPORTING_MANAGER', 'HR'], half_day_allowed=False,
        gender_restriction='F', min_service_days=80,
        can_apply_in_advance=True, can_apply_retroactively=False,
        probation_eligible=True,
        year_end_action='LAPSE',
    )
    defaults.update(overrides)
    lt = LeaveType.objects.create(**defaults)
    LeavePolicyVersion.objects.create(
        leave_type=lt, version=1, snapshot={}, change_summary='init', changed_via='API',
    )
    return lt


def _make_ptl(**overrides):
    """Create a Paternity Leave type."""
    defaults = dict(
        code='PtL', name='Paternity Leave', entitlement_days=5, credit_method='EVENT',
        approval_chain=['REPORTING_MANAGER'], half_day_allowed=False,
        gender_restriction='M', avail_window_days=90,
        can_apply_in_advance=True, can_apply_retroactively=False,
        probation_eligible=False,
        year_end_action='LAPSE',
    )
    defaults.update(overrides)
    lt = LeaveType.objects.create(**defaults)
    LeavePolicyVersion.objects.create(
        leave_type=lt, version=1, snapshot={}, change_summary='init', changed_via='API',
    )
    return lt


def _ctx(employee_id, role='EMPLOYEE'):
    """Build user_context dict."""
    return {'employee_id': employee_id, 'role': role}


def _year():
    """Current leave year (April start)."""
    today = date.today()
    return today.year if today.month >= 4 else today.year - 1


# ====================================================================
# 1. PARAMETER MAPPING TESTS
# ====================================================================

class TestParameterMapping(TestCase):
    """Verify _ARG_REMAP correctly translates argument names for each tool."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        self.sl = _make_sl()
        LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.sl, year=_year(), entitled=Decimal('8.0'),
        )

    # -- apply_leave: leave_type -> leave_type_code --
    def test_apply_leave_remap_leave_type(self):
        """apply_leave: 'leave_type' argument is remapped to 'leave_type_code'."""
        yesterday = _prev_weekday(1)
        result = execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'remap test',
        }, _ctx('EMP-001'))
        self.assertNotIn('error', result)
        self.assertEqual(result.get('status'), 'PENDING')

    # -- validate_leave: leave_type -> leave_type_code --
    def test_validate_leave_remap_leave_type(self):
        """validate_leave: 'leave_type' argument is remapped to 'leave_type_code'."""
        yesterday = _prev_weekday(1)
        result = execute_tool('validate_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
        }, _ctx('EMP-001'))
        self.assertNotIn('error', result)

    # -- adjust_balance: leave_type -> leave_type_code --
    def test_adjust_balance_remap_leave_type(self):
        """adjust_balance: 'leave_type' remapped to 'leave_type_code'."""
        result = execute_tool('adjust_balance', {
            'employee_id': 'EMP-001',
            'leave_type': 'SL',
            'days': 2,
            'reason': 'remap test',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)

    # -- get_overrides: leave_type -> leave_type_code --
    def test_get_overrides_remap_leave_type(self):
        """get_overrides: 'leave_type' remapped to 'leave_type_code'."""
        result = execute_tool('get_overrides', {
            'leave_type': 'SL',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)

    # -- trigger_bulk_credit: leave_type -> leave_type_code --
    def test_trigger_bulk_credit_remap_leave_type(self):
        """trigger_bulk_credit: 'leave_type' remapped to 'leave_type_code'."""
        result = execute_tool('trigger_bulk_credit', {
            'year': _year(),
            'leave_type': 'SL',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)

    # -- trigger_monthly_accrual: date -> execution_date --
    def test_trigger_monthly_accrual_remap_date(self):
        """trigger_monthly_accrual: 'date' remapped to 'execution_date'."""
        _make_pl()
        result = execute_tool('trigger_monthly_accrual', {
            'date': date.today().isoformat(),
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)

    # -- trigger_year_end: year -> ending_year --
    def test_trigger_year_end_remap_year(self):
        """trigger_year_end: 'year' remapped to 'ending_year'."""
        result = execute_tool('trigger_year_end', {
            'year': _year() - 1,
            'dry_run': True,
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)

    # -- create_optional_holiday: date -> date_val --
    def test_create_optional_holiday_remap_date(self):
        """create_optional_holiday: 'date' remapped to 'date_val'."""
        future = _next_weekday(30)
        result = execute_tool('create_optional_holiday', {
            'name': 'Remap Test Holiday',
            'date': future.isoformat(),
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.assertTrue(OptionalHoliday.objects.filter(name='Remap Test Holiday').exists())

    # -- transfer_employee: department_code -> department, etc. --
    def test_transfer_employee_remap_args(self):
        """transfer_employee: department_code->department, reporting_manager_id->reporting_manager, designation_title->designation."""
        new_dept = Department.objects.create(code='QA', name='Quality Assurance')
        result = execute_tool('transfer_employee', {
            'employee_id': 'EMP-001',
            'department_code': new_dept,
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)

    # -- create_leave_type: args packed into config_dict --
    def test_create_leave_type_pack_as_dict(self):
        """create_leave_type: all args are packed into config_dict."""
        result = execute_tool('create_leave_type', {
            'code': 'TST',
            'name': 'Test Leave',
            'entitlement_days': 5,
            'credit_method': 'BULK',
            'approval_chain': ['REPORTING_MANAGER'],
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.assertTrue(LeaveType.objects.filter(code='TST').exists())

    # -- update_employee: changes dict unpacked into kwargs --
    def test_update_employee_unpack_changes(self):
        """update_employee: 'changes' dict is unpacked into **kwargs."""
        result = execute_tool('update_employee', {
            'employee_id': 'EMP-001',
            'changes': {'phone': '9876543210'},
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.phone, '9876543210')

    # -- Verify date strings are parsed to date objects --
    def test_date_string_auto_parsing(self):
        """Date-like strings (YYYY-MM-DD) are automatically parsed to date objects."""
        yesterday = _prev_weekday(1)
        result = execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'date parse test',
            'idempotency_key': f'DATEPARSE_{uuid4().hex[:8]}',
        }, _ctx('EMP-001'))
        self.assertNotIn('error', result)

    # -- Verify that inject employee_id works for get_my_balance --
    def test_inject_employee_id_get_my_balance(self):
        """get_my_balance: employee_id is auto-injected from user_context."""
        result = execute_tool('get_my_balance', {}, _ctx('EMP-001'))
        self.assertNotIn('error', result)

    # -- Verify that inject employee_id works for get_my_requests --
    def test_inject_employee_id_get_my_requests(self):
        """get_my_requests: employee_id is auto-injected from user_context."""
        result = execute_tool('get_my_requests', {}, _ctx('EMP-001'))
        self.assertNotIn('error', result)

    # -- employee param injection for apply_leave --
    def test_employee_param_injection_apply(self):
        """apply_leave: employee object is injected as first positional arg."""
        yesterday = _prev_weekday(1)
        result = execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'injection test',
            'idempotency_key': f'INJ_{uuid4().hex[:8]}',
        }, _ctx('EMP-001'))
        self.assertNotIn('error', result)
        req = LeaveRequest.objects.get(id=result['id'])
        self.assertEqual(req.employee.employee_id, 'EMP-001')

    # -- approver param injection for approve_leave --
    def test_approver_param_injection(self):
        """approve_leave: approver object is injected as first positional arg."""
        yesterday = _prev_weekday(1)
        apply_result = execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'approver injection test',
            'idempotency_key': f'APPINJ_{uuid4().hex[:8]}',
        }, _ctx('EMP-001'))
        req_id = apply_result['id']
        result = execute_tool('approve_leave', {
            'request_id': req_id,
        }, _ctx('MGR-001', 'MANAGER'))
        self.assertNotIn('error', result)


# ====================================================================
# 2. EMPLOYEE TOOLS
# ====================================================================

class TestEmployeeGetBalance(TestCase):
    """Test get_my_balance tool."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        self.sl = _make_sl()
        LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.sl, year=_year(), entitled=Decimal('8.0'),
        )

    def test_get_my_balance_returns_results(self):
        """get_my_balance returns a results list with balance data."""
        result = execute_tool('get_my_balance', {}, _ctx('EMP-001'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)

    def test_get_my_balance_has_leave_type_code(self):
        """Balance entries include leave_type_code."""
        result = execute_tool('get_my_balance', {}, _ctx('EMP-001'))
        entry = result['results'][0]
        self.assertIn('leave_type_code', entry)
        self.assertEqual(entry['leave_type_code'], 'SL')

    def test_get_my_balance_has_leave_type_name(self):
        """Balance entries include leave_type_name."""
        result = execute_tool('get_my_balance', {}, _ctx('EMP-001'))
        entry = result['results'][0]
        self.assertIn('leave_type_name', entry)
        self.assertEqual(entry['leave_type_name'], 'Sick Leave')

    def test_get_my_balance_has_available(self):
        """Balance entries include 'available' computed property."""
        result = execute_tool('get_my_balance', {}, _ctx('EMP-001'))
        entry = result['results'][0]
        self.assertIn('available', entry)
        self.assertEqual(entry['available'], '8.0')

    def test_get_my_balance_with_year(self):
        """get_my_balance accepts optional year parameter."""
        result = execute_tool('get_my_balance', {'year': _year()}, _ctx('EMP-001'))
        self.assertIn('results', result)


class TestEmployeeGetRequests(TestCase):
    """Test get_my_requests tool."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        self.sl = _make_sl()
        LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.sl, year=_year(), entitled=Decimal('8.0'),
        )
        yesterday = _prev_weekday(1)
        execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'seed request',
        }, _ctx('EMP-001'))

    def test_get_my_requests_returns_results(self):
        """get_my_requests returns list of requests."""
        result = execute_tool('get_my_requests', {}, _ctx('EMP-001'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)

    def test_get_my_requests_filter_by_status(self):
        """get_my_requests filters by status."""
        result = execute_tool('get_my_requests', {'status': 'PENDING'}, _ctx('EMP-001'))
        self.assertIn('results', result)
        for entry in result['results']:
            self.assertEqual(entry['status'], 'PENDING')

    def test_get_my_requests_no_results_for_cancelled(self):
        """get_my_requests with status=CANCELLED returns empty if none exist."""
        result = execute_tool('get_my_requests', {'status': 'CANCELLED'}, _ctx('EMP-001'))
        self.assertIn('results', result)
        self.assertEqual(len(result['results']), 0)


class TestValidateLeave(TestCase):
    """Test validate_leave tool with all validation rules."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        self.sl = _make_sl()
        self.pl = _make_pl()
        self.el = _make_el()
        self.wfh = _make_wfh()
        self.ml = _make_ml()
        self.ptl = _make_ptl()
        self.lop = _make_lop()

        LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.sl, year=_year(), entitled=Decimal('8.0'),
        )
        LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.pl, year=_year(), entitled=Decimal('6.0'),
        )
        LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.el, year=_year(), entitled=Decimal('5.0'),
        )
        LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.wfh, year=_year(), entitled=Decimal('12.0'),
        )

    def test_validate_sl_retroactive_passes(self):
        """SL can be applied retroactively."""
        yesterday = _prev_weekday(1)
        result = execute_tool('validate_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
        }, _ctx('EMP-001'))
        self.assertNotIn('error', result)

    def test_validate_sl_advance_fails(self):
        """SL cannot be applied in advance (can_apply_in_advance=False)."""
        future = _next_weekday(5)
        result = execute_tool('validate_leave', {
            'leave_type': 'SL',
            'start_date': future.isoformat(),
            'end_date': future.isoformat(),
        }, _ctx('EMP-001'))
        self.assertFalse(result.get('valid', True))
        self.assertIn('cannot be applied in advance', result.get('message', ''))

    def test_validate_pl_advance_notice_required(self):
        """PL requires 2-day advance notice; applying for tomorrow (calendar day) fails."""
        # Use tomorrow (exactly 1 day notice, which is < 2 required).
        # If tomorrow is a weekend, the weekend validator will reject it instead.
        target = date.today() + timedelta(days=1)
        result = execute_tool('validate_leave', {
            'leave_type': 'PL',
            'start_date': target.isoformat(),
            'end_date': target.isoformat(),
        }, _ctx('EMP-001'))
        # Should fail — either advance notice (weekday) or weekend (Sat/Sun)
        self.assertFalse(result.get('valid', True), f"Expected invalid but got: {result}")

    def test_validate_pl_sufficient_advance_passes(self):
        """PL with enough advance notice passes."""
        future = _next_weekday(5)
        result = execute_tool('validate_leave', {
            'leave_type': 'PL',
            'start_date': future.isoformat(),
            'end_date': future.isoformat(),
        }, _ctx('EMP-001'))
        self.assertNotIn('error', result)

    def test_validate_el_advance_notice_3_days(self):
        """EL requires 3-day advance notice."""
        near_future = _next_weekday(2)
        result = execute_tool('validate_leave', {
            'leave_type': 'EL',
            'start_date': near_future.isoformat(),
            'end_date': near_future.isoformat(),
        }, _ctx('EMP-001'))
        self.assertFalse(result.get('valid', True))
        self.assertIn('advance notice', result.get('message', ''))

    def test_validate_gender_restriction_ml(self):
        """ML is restricted to female employees."""
        # EMP-001 is male
        future = _next_weekday(5)
        result = execute_tool('validate_leave', {
            'leave_type': 'ML',
            'start_date': future.isoformat(),
            'end_date': future.isoformat(),
        }, _ctx('EMP-001'))
        self.assertFalse(result.get('valid', True))
        self.assertIn('gender', result.get('message', '').lower())

    def test_validate_gender_restriction_ptl_female_fails(self):
        """PtL is restricted to male employees, so female employees are rejected."""
        female_emp = Employee.objects.create(
            employee_id='EMP-F01', first_name='Fiona', last_name='Dev',
            email='fiona@test.co', gender='F', department=self.dept, designation=self.desg,
            date_of_joining=date(2024, 1, 1), probation_status='CONFIRMED',
            reporting_manager=self.manager,
        )
        future = _next_weekday(5)
        result = execute_tool('validate_leave', {
            'leave_type': 'PtL',
            'start_date': future.isoformat(),
            'end_date': future.isoformat(),
        }, _ctx('EMP-F01'))
        self.assertFalse(result.get('valid', True))
        self.assertIn('gender', result.get('message', '').lower())

    def test_validate_probation_wfh_blocked(self):
        """WFH is not available during probation."""
        probation_emp = Employee.objects.create(
            employee_id='EMP-PROB', first_name='Probie', last_name='Dev',
            email='probie@test.co', gender='M', department=self.dept, designation=self.desg,
            date_of_joining=date(2026, 3, 1), probation_status='ON_PROBATION',
            reporting_manager=self.manager,
        )
        LeaveBalance.objects.create(
            employee=probation_emp, leave_type=self.wfh, year=_year(), entitled=Decimal('12.0'),
        )
        future = _next_weekday(5)
        result = execute_tool('validate_leave', {
            'leave_type': 'WFH',
            'start_date': future.isoformat(),
            'end_date': future.isoformat(),
        }, _ctx('EMP-PROB'))
        self.assertFalse(result.get('valid', True))
        self.assertIn('probation', result.get('message', '').lower())

    def test_validate_insufficient_balance(self):
        """Validation fails when balance is insufficient."""
        # Set balance to 0
        bal = LeaveBalance.objects.get(employee=self.emp, leave_type=self.sl, year=_year())
        bal.used = Decimal('8.0')
        bal.save()

        yesterday = _prev_weekday(1)
        result = execute_tool('validate_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
        }, _ctx('EMP-001'))
        self.assertFalse(result.get('valid', True))
        self.assertIn('nsufficient balance', result.get('message', ''))

    def test_validate_lop_no_balance_check(self):
        """LOP (ON_DEMAND credit) skips balance check."""
        yesterday = _prev_weekday(1)
        result = execute_tool('validate_leave', {
            'leave_type': 'LOP',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
        }, _ctx('EMP-001'))
        self.assertNotIn('error', result)

    def test_validate_half_day_requires_period(self):
        """Half-day leave must specify AM or PM."""
        yesterday = _prev_weekday(1)
        result = execute_tool('validate_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'is_half_day': True,
        }, _ctx('EMP-001'))
        self.assertFalse(result.get('valid', True))
        self.assertIn('AM/PM', result.get('message', ''))

    def test_validate_half_day_multi_day_fails(self):
        """Half-day leave must be for a single day."""
        d1 = _prev_weekday(2)
        d2 = _prev_weekday(1)
        result = execute_tool('validate_leave', {
            'leave_type': 'SL',
            'start_date': d1.isoformat(),
            'end_date': d2.isoformat(),
            'is_half_day': True,
            'half_day_period': 'AM',
        }, _ctx('EMP-001'))
        self.assertFalse(result.get('valid', True))
        self.assertIn('single day', result.get('message', ''))

    def test_validate_weekend_only_fails(self):
        """Dates that fall entirely on weekends fail validation."""
        # Find the next Saturday
        d = date.today()
        while d.weekday() != 5:
            d += timedelta(days=1)
        sunday = d + timedelta(days=1)
        result = execute_tool('validate_leave', {
            'leave_type': 'SL',
            'start_date': d.isoformat(),
            'end_date': sunday.isoformat(),
        }, _ctx('EMP-001'))
        self.assertFalse(result.get('valid', True))
        self.assertIn('weekend', result.get('message', '').lower())

    def test_validate_overlap_detected(self):
        """Overlapping leave requests are detected."""
        yesterday = _prev_weekday(1)
        execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'first',
        }, _ctx('EMP-001'))
        result = execute_tool('validate_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
        }, _ctx('EMP-001'))
        self.assertFalse(result.get('valid', True))
        self.assertIn('verlapping', result.get('message', ''))

    def test_validate_pl_retroactive_fails(self):
        """PL cannot be applied retroactively (can_apply_retroactively=False)."""
        yesterday = _prev_weekday(1)
        result = execute_tool('validate_leave', {
            'leave_type': 'PL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
        }, _ctx('EMP-001'))
        self.assertFalse(result.get('valid', True), f"Expected invalid but got: {result}")
        # Either retroactive or advance notice message is acceptable
        msg = result.get('message', '')
        self.assertTrue('retroactively' in msg or 'advance notice' in msg,
                        f"Expected retroactive or advance notice error, got: {msg}")


class TestApplyLeave(TestCase):
    """Test apply_leave tool."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        self.sl = _make_sl()
        self.lop = _make_lop()
        self.balance = LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.sl, year=_year(), entitled=Decimal('8.0'),
        )

    def test_apply_leave_creates_pending_request(self):
        """apply_leave creates a PENDING request and returns its data."""
        yesterday = _prev_weekday(1)
        result = execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'feeling unwell',
        }, _ctx('EMP-001'))
        self.assertNotIn('error', result)
        self.assertEqual(result['status'], 'PENDING')
        self.assertIn('id', result)

    def test_apply_leave_balance_hold(self):
        """Applying leave places a hold on the balance (pending increases)."""
        yesterday = _prev_weekday(1)
        execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'balance hold test',
        }, _ctx('EMP-001'))
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.pending, Decimal('1.0'))

    def test_apply_leave_lop_no_balance_hold(self):
        """LOP (ON_DEMAND) does not place a balance hold."""
        yesterday = _prev_weekday(1)
        result = execute_tool('apply_leave', {
            'leave_type': 'LOP',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'LOP test',
        }, _ctx('EMP-001'))
        self.assertNotIn('error', result)
        # No LeaveBalance for LOP should have been modified
        self.assertFalse(
            LeaveBalance.objects.filter(employee=self.emp, leave_type=self.lop).exists()
        )

    def test_apply_leave_idempotency(self):
        """Duplicate apply_leave with same idempotency_key returns cached result."""
        idem_key = f'TEST_{uuid4().hex[:8]}'
        yesterday = _prev_weekday(1)
        args = {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'idempotency test',
            'idempotency_key': idem_key,
        }
        result1 = execute_tool('apply_leave', args, _ctx('EMP-001'))
        result2 = execute_tool('apply_leave', args, _ctx('EMP-001'))
        # Second call should return cached result, not create a new request
        self.assertEqual(LeaveRequest.objects.filter(
            employee=self.emp, leave_type=self.sl, reason='idempotency test'
        ).count(), 1)

    def test_apply_leave_invalid_type_fails(self):
        """apply_leave with a non-existent leave type code returns error."""
        yesterday = _prev_weekday(1)
        result = execute_tool('apply_leave', {
            'leave_type': 'NONEXISTENT',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'bad type',
        }, _ctx('EMP-001'))
        self.assertIn('error', result)

    def test_apply_leave_half_day(self):
        """apply_leave with half day option produces 0.5 duration."""
        yesterday = _prev_weekday(1)
        result = execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'half day test',
            'is_half_day': True,
            'half_day_period': 'AM',
        }, _ctx('EMP-001'))
        self.assertNotIn('error', result)
        self.assertEqual(result['duration_days'], '0.5')

    def test_apply_leave_assigns_approver(self):
        """apply_leave sets the current_approver to the reporting manager."""
        yesterday = _prev_weekday(1)
        result = execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'approver test',
            'idempotency_key': f'APPR_{uuid4().hex[:8]}',
        }, _ctx('EMP-001'))
        req = LeaveRequest.objects.get(id=result['id'])
        self.assertEqual(req.current_approver, self.manager)


class TestCancelLeave(TestCase):
    """Test cancel_leave tool."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        self.sl = _make_sl()
        self.balance = LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.sl, year=_year(), entitled=Decimal('8.0'),
        )

    def _apply_sl(self):
        """Helper: apply a 1-day SL and return its id."""
        yesterday = _prev_weekday(1)
        result = execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'for cancel test',
            'idempotency_key': f'CANC_{uuid4().hex[:8]}',
        }, _ctx('EMP-001'))
        return result['id']

    def test_cancel_pending_releases_hold(self):
        """Cancelling a PENDING request releases the balance hold."""
        req_id = self._apply_sl()
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.pending, Decimal('1.0'))

        result = execute_tool('cancel_leave', {
            'request_id': req_id,
            'reason': 'changed mind',
        }, _ctx('EMP-001'))
        self.assertNotIn('error', result)
        self.assertEqual(result['status'], 'CANCELLED')

        self.balance.refresh_from_db()
        self.assertEqual(self.balance.pending, Decimal('0.0'))

    def test_cancel_approved_reverses_used(self):
        """Cancelling an APPROVED request reverses the 'used' amount."""
        req_id = self._apply_sl()
        # Approve first
        execute_tool('approve_leave', {'request_id': req_id}, _ctx('MGR-001', 'MANAGER'))
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.used, Decimal('1.0'))

        result = execute_tool('cancel_leave', {
            'request_id': req_id,
            'reason': 'cancel approved',
        }, _ctx('EMP-001'))
        self.assertNotIn('error', result)

        self.balance.refresh_from_db()
        self.assertEqual(self.balance.used, Decimal('0.0'))

    def test_cancel_other_employee_fails(self):
        """Cannot cancel another employee's leave request."""
        req_id = self._apply_sl()
        # Try to cancel as manager (not the owner)
        result = execute_tool('cancel_leave', {
            'request_id': req_id,
        }, _ctx('MGR-001', 'MANAGER'))
        self.assertIn('error', result)
        self.assertIn('your own', result['error'])

    def test_cancel_already_cancelled_fails(self):
        """Cannot cancel an already cancelled request."""
        req_id = self._apply_sl()
        execute_tool('cancel_leave', {'request_id': req_id}, _ctx('EMP-001'))
        result = execute_tool('cancel_leave', {'request_id': req_id}, _ctx('EMP-001'))
        self.assertIn('error', result)
        self.assertIn('CANCELLED', result['error'])


class TestGetLeavePolicy(TestCase):
    """Test get_leave_policy tool."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        _make_sl()
        _make_pl()
        _make_el()

    def test_get_leave_policy_returns_results(self):
        """get_leave_policy returns list of active leave types."""
        result = execute_tool('get_leave_policy', {}, _ctx('EMP-001'))
        self.assertIn('results', result)
        self.assertGreaterEqual(len(result['results']), 3)

    def test_get_leave_policy_contains_sl(self):
        """get_leave_policy includes Sick Leave."""
        result = execute_tool('get_leave_policy', {}, _ctx('EMP-001'))
        codes = [r.get('code') for r in result['results']]
        self.assertIn('SL', codes)


class TestOptionalHolidays(TestCase):
    """Test optional holiday tools (employee + admin)."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()

    def test_create_optional_holiday(self):
        """Admin can create an optional holiday."""
        future = _next_weekday(60)
        result = execute_tool('create_optional_holiday', {
            'name': 'Test Holiday',
            'date': future.isoformat(),
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.assertTrue(OptionalHoliday.objects.filter(name='Test Holiday').exists())

    def test_get_optional_holidays(self):
        """Employee can list optional holidays."""
        future = _next_weekday(60)
        OptionalHoliday.objects.create(
            name='Diwali', date=future, year=future.year, created_by=self.hr,
        )
        result = execute_tool('get_optional_holidays', {'year': future.year}, _ctx('EMP-001'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)

    def test_select_optional_holiday(self):
        """Employee can select an optional holiday."""
        future = _next_weekday(60)
        holiday = OptionalHoliday.objects.create(
            name='Pongal', date=future, year=future.year, created_by=self.hr,
        )
        result = execute_tool('select_optional_holiday', {
            'holiday_id': holiday.id,
        }, _ctx('EMP-001'))
        self.assertNotIn('error', result)
        self.assertTrue(OptionalHolidaySelection.objects.filter(
            employee=self.emp, holiday=holiday,
        ).exists())

    def test_approve_optional_holiday_selection(self):
        """Manager can approve an optional holiday selection."""
        future = _next_weekday(60)
        holiday = OptionalHoliday.objects.create(
            name='Eid', date=future, year=future.year, created_by=self.hr,
        )
        sel = OptionalHolidaySelection.objects.create(
            employee=self.emp, holiday=holiday, status='PENDING',
        )
        result = execute_tool('approve_optional_holiday', {
            'selection_id': sel.id,
        }, _ctx('MGR-001', 'MANAGER'))
        self.assertNotIn('error', result)
        sel.refresh_from_db()
        self.assertEqual(sel.status, 'APPROVED')


# ====================================================================
# 3. MANAGER TOOLS
# ====================================================================

class TestManagerApproval(TestCase):
    """Test approve_leave and reject_leave tools."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        self.sl = _make_sl()
        self.balance = LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.sl, year=_year(), entitled=Decimal('8.0'),
        )

    def _apply_sl(self):
        yesterday = _prev_weekday(1)
        result = execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'for approval test',
            'idempotency_key': f'APRVTEST_{uuid4().hex[:8]}',
        }, _ctx('EMP-001'))
        return result['id']

    def test_approve_leave_success(self):
        """Manager approves a pending leave request."""
        req_id = self._apply_sl()
        result = execute_tool('approve_leave', {
            'request_id': req_id,
            'remarks': 'approved',
        }, _ctx('MGR-001', 'MANAGER'))
        self.assertNotIn('error', result)
        self.assertEqual(result['status'], 'APPROVED')

    def test_approve_leave_updates_balance(self):
        """Approval moves balance from pending to used."""
        req_id = self._apply_sl()
        execute_tool('approve_leave', {'request_id': req_id}, _ctx('MGR-001', 'MANAGER'))
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.pending, Decimal('0.0'))
        self.assertEqual(self.balance.used, Decimal('1.0'))

    def test_approve_leave_wrong_approver_fails(self):
        """Non-assigned approver cannot approve."""
        req_id = self._apply_sl()
        # HR is not the assigned approver for SL
        result = execute_tool('approve_leave', {
            'request_id': req_id,
        }, _ctx('HR-001', 'ADMIN'))
        self.assertIn('error', result)
        self.assertIn('not the current approver', result['error'])

    def test_approve_already_approved_fails(self):
        """Cannot approve an already approved request."""
        req_id = self._apply_sl()
        execute_tool('approve_leave', {'request_id': req_id}, _ctx('MGR-001', 'MANAGER'))
        result = execute_tool('approve_leave', {
            'request_id': req_id,
        }, _ctx('MGR-001', 'MANAGER'))
        self.assertIn('error', result)
        self.assertIn('not pending', result['error'].lower())

    def test_reject_leave_success(self):
        """Manager rejects a pending leave request."""
        req_id = self._apply_sl()
        result = execute_tool('reject_leave', {
            'request_id': req_id,
            'remarks': 'project deadline',
        }, _ctx('MGR-001', 'MANAGER'))
        self.assertNotIn('error', result)
        self.assertEqual(result['status'], 'REJECTED')

    def test_reject_leave_releases_balance(self):
        """Rejection releases the balance hold."""
        req_id = self._apply_sl()
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.pending, Decimal('1.0'))

        execute_tool('reject_leave', {
            'request_id': req_id,
            'remarks': 'not now',
        }, _ctx('MGR-001', 'MANAGER'))
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.pending, Decimal('0.0'))

    def test_reject_leave_wrong_approver_fails(self):
        """Non-assigned approver cannot reject."""
        req_id = self._apply_sl()
        result = execute_tool('reject_leave', {
            'request_id': req_id,
            'remarks': 'unauthorized',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertIn('error', result)
        self.assertIn('not the current approver', result['error'])


class TestManagerTeamTools(TestCase):
    """Test get_team_requests, get_team_balance, get_team_calendar."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        self.sl = _make_sl()
        self.balance = LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.sl, year=_year(), entitled=Decimal('8.0'),
        )

    def test_get_team_requests_shows_report_leaves(self):
        """get_team_requests returns leaves from direct reports."""
        yesterday = _prev_weekday(1)
        execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'team view test',
        }, _ctx('EMP-001'))
        result = execute_tool('get_team_requests', {}, _ctx('MGR-001', 'MANAGER'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)

    def test_get_team_requests_filter_by_status(self):
        """get_team_requests can filter by status."""
        result = execute_tool('get_team_requests', {
            'status': 'APPROVED',
        }, _ctx('MGR-001', 'MANAGER'))
        self.assertIn('results', result)

    def test_get_team_balance(self):
        """get_team_balance returns balances of direct reports."""
        result = execute_tool('get_team_balance', {}, _ctx('MGR-001', 'MANAGER'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)

    def test_get_team_calendar(self):
        """get_team_calendar returns approved leave entries in date range."""
        yesterday = _prev_weekday(1)
        # Apply and approve to get an approved leave in the calendar
        apply_res = execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'calendar test',
            'idempotency_key': f'CAL_{uuid4().hex[:8]}',
        }, _ctx('EMP-001'))
        execute_tool('approve_leave', {
            'request_id': apply_res['id'],
        }, _ctx('MGR-001', 'MANAGER'))

        start = (date.today() - timedelta(days=7)).isoformat()
        end = (date.today() + timedelta(days=7)).isoformat()
        result = execute_tool('get_team_calendar', {
            'start_date': start,
            'end_date': end,
        }, _ctx('MGR-001', 'MANAGER'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)

    def test_get_team_requests_no_reports_empty(self):
        """Manager with no reports sees empty team requests."""
        result = execute_tool('get_team_requests', {}, _ctx('HR-001', 'MANAGER'))
        self.assertIn('results', result)
        self.assertEqual(len(result['results']), 0)


# ====================================================================
# 4. ADMIN TOOLS
# ====================================================================

class TestAdminLeaveTypeTools(TestCase):
    """Test create_leave_type, update_leave_type, deactivate_leave_type."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()

    def test_create_leave_type(self):
        """Admin creates a new leave type via config_dict packing."""
        result = execute_tool('create_leave_type', {
            'code': 'CL',
            'name': 'Compensatory Leave',
            'entitlement_days': 5,
            'credit_method': 'BULK',
            'approval_chain': ['REPORTING_MANAGER'],
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.assertTrue(LeaveType.objects.filter(code='CL').exists())

    def test_create_leave_type_creates_version(self):
        """Creating a leave type also creates an initial policy version."""
        execute_tool('create_leave_type', {
            'code': 'CL2',
            'name': 'Comp Leave 2',
            'entitlement_days': 3,
            'credit_method': 'BULK',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertTrue(LeavePolicyVersion.objects.filter(
            leave_type__code='CL2', version=1,
        ).exists())

    def test_update_leave_type_prospective(self):
        """Admin updates a leave type with PROSPECTIVE mode."""
        _make_sl()
        result = execute_tool('update_leave_type', {
            'code': 'SL',
            'changes': {'entitlement_days': 10},
            'change_summary': 'Increased SL entitlement',
            'effective_mode': 'PROSPECTIVE',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        sl = LeaveType.objects.get(code='SL')
        self.assertEqual(sl.entitlement_days, 10)

    def test_update_leave_type_creates_new_version(self):
        """Updating a leave type creates a new policy version."""
        _make_sl()
        execute_tool('update_leave_type', {
            'code': 'SL',
            'changes': {'half_day_allowed': False},
            'change_summary': 'Disabled half day',
        }, _ctx('HR-001', 'ADMIN'))
        versions = LeavePolicyVersion.objects.filter(leave_type__code='SL')
        self.assertEqual(versions.count(), 2)

    def test_update_leave_type_retroactive(self):
        """Admin updates a leave type with RETROACTIVE mode."""
        _make_sl()
        result = execute_tool('update_leave_type', {
            'code': 'SL',
            'changes': {'advance_notice_days': 1},
            'change_summary': 'Added 1-day notice for SL',
            'effective_mode': 'RETROACTIVE',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)

    def test_deactivate_leave_type(self):
        """Admin deactivates a leave type."""
        _make_sl()
        result = execute_tool('deactivate_leave_type', {
            'code': 'SL',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        sl = LeaveType.objects.get(code='SL')
        self.assertFalse(sl.is_active)


class TestAdminOverrideTools(TestCase):
    """Test create_override, remove_override, get_overrides."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        self.sl = _make_sl()

    def test_create_override_block_application(self):
        """Admin creates an override that blocks leave application."""
        result = execute_tool('create_override', {
            'employee_id': 'EMP-001',
            'leave_type_code': 'SL',
            'block_application': True,
            'effective_from': date.today().isoformat(),
            'reason': 'test block',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.assertTrue(EmployeeOverride.objects.filter(
            employee=self.emp, block_application=True,
        ).exists())

    def test_override_actually_blocks_application(self):
        """An override with block_application=True prevents leave application."""
        past = (date.today() - timedelta(days=30)).isoformat()
        execute_tool('create_override', {
            'employee_id': 'EMP-001',
            'leave_type_code': 'SL',
            'block_application': True,
            'effective_from': past,
            'reason': 'block test',
        }, _ctx('HR-001', 'ADMIN'))
        LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.sl, year=_year(), entitled=Decimal('8.0'),
        )
        yesterday = _prev_weekday(1)
        result = execute_tool('validate_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
        }, _ctx('EMP-001'))
        self.assertFalse(result.get('valid', True))
        self.assertIn('blocked', result.get('message', '').lower())

    def test_remove_override(self):
        """Admin removes (deactivates) an override."""
        override = EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.sl,
            block_application=True,
            effective_from=date.today(),
            reason='temp block',
            created_by=self.hr, created_via='API',
        )
        result = execute_tool('remove_override', {
            'override_id': override.id,
            'reason': 'no longer needed',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        override.refresh_from_db()
        self.assertFalse(override.is_active)

    def test_get_overrides_by_employee(self):
        """get_overrides filters by employee_id."""
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.sl,
            block_accrual=True,
            effective_from=date.today(),
            reason='test',
            created_by=self.hr, created_via='API',
        )
        result = execute_tool('get_overrides', {
            'employee_id': 'EMP-001',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)

    def test_get_overrides_by_leave_type(self):
        """get_overrides filters by leave_type (remapped from leave_type)."""
        EmployeeOverride.objects.create(
            employee=self.emp, leave_type=self.sl,
            block_application=True,
            effective_from=date.today(),
            reason='test',
            created_by=self.hr, created_via='API',
        )
        result = execute_tool('get_overrides', {
            'leave_type': 'SL',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)


class TestAdminBalanceAdjust(TestCase):
    """Test adjust_balance tool."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        self.sl = _make_sl()
        self.balance = LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.sl, year=_year(), entitled=Decimal('8.0'),
        )

    def test_adjust_balance_positive(self):
        """Positive adjustment increases the balance."""
        result = execute_tool('adjust_balance', {
            'employee_id': 'EMP-001',
            'leave_type': 'SL',
            'days': 3,
            'reason': 'bonus days',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.adjusted, Decimal('3.0'))

    def test_adjust_balance_negative(self):
        """Negative adjustment decreases the balance."""
        result = execute_tool('adjust_balance', {
            'employee_id': 'EMP-001',
            'leave_type': 'SL',
            'days': -2,
            'reason': 'correction',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.adjusted, Decimal('-2.0'))

    def test_adjust_balance_creates_ledger_entry(self):
        """Adjustment creates a ledger entry."""
        execute_tool('adjust_balance', {
            'employee_id': 'EMP-001',
            'leave_type': 'SL',
            'days': 1,
            'reason': 'ledger test',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertTrue(LeaveBalanceLedger.objects.filter(
            employee=self.emp,
            leave_type=self.sl,
            txn_type='CREDIT_ADJUSTMENT',
        ).exists())

    def test_adjust_balance_negative_creates_debit_ledger(self):
        """Negative adjustment creates a DEBIT_ADJUSTMENT ledger entry."""
        execute_tool('adjust_balance', {
            'employee_id': 'EMP-001',
            'leave_type': 'SL',
            'days': -1,
            'reason': 'debit test',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertTrue(LeaveBalanceLedger.objects.filter(
            employee=self.emp,
            leave_type=self.sl,
            txn_type='DEBIT_ADJUSTMENT',
        ).exists())


class TestAdminEmployeeMgmt(TestCase):
    """Test add_employee, update_employee, confirm_employee, deactivate_employee, transfer_employee, get_employee, search_employees."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()

    def test_add_employee(self):
        """Admin adds a new employee."""
        result = execute_tool('add_employee', {
            'employee_id': 'NEW-001',
            'first_name': 'New',
            'last_name': 'Joiner',
            'email': 'new001@test.co',
            'gender': 'M',
            'department': self.dept,
            'designation': self.desg,
            'date_of_joining': date.today().isoformat(),
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.assertTrue(Employee.objects.filter(employee_id='NEW-001').exists())

    def test_add_employee_creates_hr_action(self):
        """Adding an employee creates a NEW_JOINER HR action."""
        execute_tool('add_employee', {
            'employee_id': 'NEW-002',
            'first_name': 'Another',
            'email': 'new002@test.co',
            'gender': 'F',
            'department': self.dept,
            'designation': self.desg,
            'date_of_joining': date.today().isoformat(),
        }, _ctx('HR-001', 'ADMIN'))
        self.assertTrue(PendingHRAction.objects.filter(
            trigger_type='NEW_JOINER',
            employee__employee_id='NEW-002',
        ).exists())

    def test_update_employee_changes(self):
        """Admin updates employee fields via changes dict unpacking."""
        result = execute_tool('update_employee', {
            'employee_id': 'EMP-001',
            'changes': {'phone': '1111111111'},
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.phone, '1111111111')

    def test_confirm_employee(self):
        """Admin confirms an employee (ends probation)."""
        probation_emp = Employee.objects.create(
            employee_id='PROB-001', first_name='Probie', last_name='Test',
            email='probie001@test.co', gender='M', department=self.dept, designation=self.desg,
            date_of_joining=date(2025, 10, 1), probation_status='ON_PROBATION',
        )
        result = execute_tool('confirm_employee', {
            'employee_id': 'PROB-001',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        probation_emp.refresh_from_db()
        self.assertEqual(probation_emp.probation_status, 'CONFIRMED')

    def test_deactivate_employee(self):
        """Admin deactivates an employee."""
        result = execute_tool('deactivate_employee', {
            'employee_id': 'EMP-001',
            'last_working_date': date.today().isoformat(),
            'exit_reason': 'RESIGNED',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.emp.refresh_from_db()
        self.assertFalse(self.emp.is_active)

    def test_deactivate_employee_creates_hr_action(self):
        """Deactivating an employee creates an EXIT HR action."""
        execute_tool('deactivate_employee', {
            'employee_id': 'EMP-001',
            'last_working_date': date.today().isoformat(),
            'exit_reason': 'TERMINATED',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertTrue(PendingHRAction.objects.filter(
            trigger_type='EXIT',
            employee=self.emp,
        ).exists())

    def test_transfer_employee(self):
        """Admin transfers employee to a different department."""
        new_dept = Department.objects.create(code='FIN', name='Finance')
        result = execute_tool('transfer_employee', {
            'employee_id': 'EMP-001',
            'department_code': new_dept,
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)

    def test_get_employee(self):
        """Admin retrieves full employee details."""
        result = execute_tool('get_employee', {
            'employee_id': 'EMP-001',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.assertEqual(result.get('employee_id'), 'EMP-001')

    def test_search_employees_by_department(self):
        """Admin searches employees by department."""
        result = execute_tool('search_employees', {
            'department': 'ENG',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)

    def test_search_employees_by_name(self):
        """Admin searches employees by name."""
        result = execute_tool('search_employees', {
            'name': 'Alice',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)

    def test_search_employees_no_results(self):
        """Searching for a non-existent name returns empty results."""
        result = execute_tool('search_employees', {
            'name': 'Nonexistent',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertIn('results', result)
        self.assertEqual(len(result['results']), 0)


class TestAdminOrgTools(TestCase):
    """Test department and team management tools."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()

    def test_create_department(self):
        """Admin creates a new department."""
        result = execute_tool('create_department', {
            'name': 'Marketing',
            'code': 'MKT',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.assertTrue(Department.objects.filter(code='MKT').exists())

    def test_update_department(self):
        """Admin updates department details."""
        result = execute_tool('update_department', {
            'code': 'ENG',
            'name': 'Engineering & DevOps',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.dept.refresh_from_db()
        self.assertEqual(self.dept.name, 'Engineering & DevOps')

    def test_list_departments(self):
        """Admin lists all departments."""
        result = execute_tool('list_departments', {}, _ctx('HR-001', 'ADMIN'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)

    def test_create_team(self):
        """Admin creates a new team."""
        result = execute_tool('create_team', {
            'name': 'Platform',
            'code': 'PLAT',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.assertTrue(Team.objects.filter(code='PLAT').exists())

    def test_update_team(self):
        """Admin updates team details."""
        team = Team.objects.create(name='Mobile', code='MOB')
        result = execute_tool('update_team', {
            'code': 'MOB',
            'name': 'Mobile Development',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        team.refresh_from_db()
        self.assertEqual(team.name, 'Mobile Development')

    def test_list_teams(self):
        """Admin lists all teams."""
        Team.objects.create(name='Backend', code='BACK')
        result = execute_tool('list_teams', {}, _ctx('HR-001', 'ADMIN'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)

    def test_add_to_team(self):
        """Admin adds an employee to a team."""
        team = Team.objects.create(name='Frontend', code='FE')
        result = execute_tool('add_to_team', {
            'employee_id': 'EMP-001',
            'team_code': 'FE',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.assertTrue(self.emp.teams.filter(code='FE').exists())

    def test_remove_from_team(self):
        """Admin removes an employee from a team."""
        team = Team.objects.create(name='DevOps', code='DO')
        self.emp.teams.add(team)
        result = execute_tool('remove_from_team', {
            'employee_id': 'EMP-001',
            'team_code': 'DO',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.assertFalse(self.emp.teams.filter(code='DO').exists())


class TestAdminAccrualTools(TestCase):
    """Test trigger_bulk_credit, trigger_monthly_accrual, trigger_year_end."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()

    def test_trigger_bulk_credit(self):
        """trigger_bulk_credit credits BULK-type leaves."""
        _make_sl()
        result = execute_tool('trigger_bulk_credit', {
            'year': _year(),
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)

    def test_trigger_bulk_credit_specific_type(self):
        """trigger_bulk_credit with leave_type filters to that type."""
        _make_sl()
        _make_wfh()
        result = execute_tool('trigger_bulk_credit', {
            'year': _year(),
            'leave_type': 'SL',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)

    def test_trigger_monthly_accrual(self):
        """trigger_monthly_accrual runs accrual for MONTHLY-type leaves."""
        _make_pl()
        result = execute_tool('trigger_monthly_accrual', {
            'date': date.today().isoformat(),
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)

    def test_trigger_monthly_accrual_no_date(self):
        """trigger_monthly_accrual without date uses today."""
        _make_pl()
        result = execute_tool('trigger_monthly_accrual', {}, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)

    def test_trigger_year_end_dry_run(self):
        """trigger_year_end with dry_run does not modify balances."""
        _make_sl()
        LeaveBalance.objects.create(
            employee=self.emp, leave_type=LeaveType.objects.get(code='SL'),
            year=_year() - 1, entitled=Decimal('8.0'),
        )
        result = execute_tool('trigger_year_end', {
            'year': _year() - 1,
            'dry_run': True,
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)

    def test_trigger_year_end_actual(self):
        """trigger_year_end executes year-end processing."""
        sl = _make_sl()  # LAPSE
        LeaveBalance.objects.create(
            employee=self.emp, leave_type=sl,
            year=_year() - 1, entitled=Decimal('8.0'),
        )
        result = execute_tool('trigger_year_end', {
            'year': _year() - 1,
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)


class TestAdminHRActions(TestCase):
    """Test get_pending_hr_actions, resolve_hr_action, execute_suggested_action."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()

    def test_get_pending_hr_actions(self):
        """get_pending_hr_actions returns OPEN actions."""
        PendingHRAction.objects.create(
            trigger_type='NEW_JOINER', employee=self.emp,
            title='Test action', description='Test', priority='LOW',
        )
        result = execute_tool('get_pending_hr_actions', {}, _ctx('HR-001', 'ADMIN'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)

    def test_get_pending_hr_actions_filter_priority(self):
        """get_pending_hr_actions filters by priority."""
        PendingHRAction.objects.create(
            trigger_type='NEW_JOINER', employee=self.emp,
            title='High priority', description='Test', priority='HIGH',
        )
        PendingHRAction.objects.create(
            trigger_type='NEW_JOINER', employee=self.emp,
            title='Low priority', description='Test', priority='LOW',
        )
        result = execute_tool('get_pending_hr_actions', {
            'priority': 'HIGH',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertIn('results', result)
        for entry in result['results']:
            self.assertEqual(entry.get('priority'), 'HIGH')

    def test_resolve_hr_action(self):
        """Admin resolves an HR action."""
        action = PendingHRAction.objects.create(
            trigger_type='NEW_JOINER', employee=self.emp,
            title='Resolve test', description='Test', priority='LOW',
        )
        result = execute_tool('resolve_hr_action', {
            'action_id': action.id,
            'status': 'RESOLVED',
            'notes': 'All good',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        action.refresh_from_db()
        self.assertEqual(action.status, 'RESOLVED')

    def test_dismiss_hr_action(self):
        """Admin dismisses an HR action."""
        action = PendingHRAction.objects.create(
            trigger_type='NEW_JOINER', employee=self.emp,
            title='Dismiss test', description='Test', priority='LOW',
        )
        result = execute_tool('resolve_hr_action', {
            'action_id': action.id,
            'status': 'DISMISSED',
            'notes': 'Not needed',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        action.refresh_from_db()
        self.assertEqual(action.status, 'DISMISSED')

    def test_execute_suggested_action_invalid_index(self):
        """execute_suggested_action with invalid index returns error."""
        action = PendingHRAction.objects.create(
            trigger_type='NEW_JOINER', employee=self.emp,
            title='Suggestion test', description='Test', priority='LOW',
            suggested_actions=[],
        )
        result = execute_tool('execute_suggested_action', {
            'action_id': action.id,
            'suggestion_index': 0,
        }, _ctx('HR-001', 'ADMIN'))
        self.assertIn('error', result)
        self.assertIn('Invalid suggestion', result['error'])


class TestAdminBatchTools(TestCase):
    """Test bulk_create_overrides, confirm_batch, rollback_batch."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        self.sl = _make_sl()

    def test_bulk_create_overrides(self):
        """bulk_create_overrides creates a PENDING_CONFIRMATION batch."""
        result = execute_tool('bulk_create_overrides', {
            'filter_criteria': {'department': 'ENG'},
            'override_template': {
                'leave_type_code': 'SL',
                'block_application': True,
                'effective_from': date.today().isoformat(),
                'reason': 'bulk test',
            },
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.assertTrue(BatchOperation.objects.filter(status='PENDING_CONFIRMATION').exists())

    def test_confirm_batch(self):
        """confirm_batch executes a pending batch."""
        batch_result = execute_tool('bulk_create_overrides', {
            'filter_criteria': {'department': 'ENG'},
            'override_template': {
                'leave_type_code': 'SL',
                'block_application': True,
                'effective_from': str(date.today()),
                'reason': 'confirm test',
            },
        }, _ctx('HR-001', 'ADMIN'))
        batch_id = batch_result['id']
        result = execute_tool('confirm_batch', {
            'batch_id': batch_id,
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        batch = BatchOperation.objects.get(id=batch_id)
        self.assertEqual(batch.status, 'EXECUTED')

    def test_rollback_batch(self):
        """rollback_batch deactivates overrides created by a batch."""
        batch_result = execute_tool('bulk_create_overrides', {
            'filter_criteria': {'department': 'ENG'},
            'override_template': {
                'leave_type_code': 'SL',
                'block_accrual': True,
                'effective_from': str(date.today()),
                'reason': 'rollback test',
            },
        }, _ctx('HR-001', 'ADMIN'))
        batch_id = batch_result['id']
        execute_tool('confirm_batch', {'batch_id': batch_id}, _ctx('HR-001', 'ADMIN'))

        result = execute_tool('rollback_batch', {
            'batch_id': batch_id,
            'reason': 'oops',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        batch = BatchOperation.objects.get(id=batch_id)
        self.assertEqual(batch.status, 'ROLLED_BACK')

    def test_confirm_already_executed_fails(self):
        """Cannot confirm an already executed batch."""
        batch_result = execute_tool('bulk_create_overrides', {
            'filter_criteria': {'department': 'ENG'},
            'override_template': {
                'leave_type_code': 'SL',
                'block_application': True,
                'effective_from': str(date.today()),
                'reason': 'double confirm',
            },
        }, _ctx('HR-001', 'ADMIN'))
        batch_id = batch_result['id']
        execute_tool('confirm_batch', {'batch_id': batch_id}, _ctx('HR-001', 'ADMIN'))
        result = execute_tool('confirm_batch', {'batch_id': batch_id}, _ctx('HR-001', 'ADMIN'))
        self.assertIn('error', result)
        self.assertIn('not pending', result['error'].lower())


class TestAdminFallbackTools(TestCase):
    """Test set_fallback_manager tool."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        self.alt_mgr = Employee.objects.create(
            employee_id='MGR-002', first_name='Backup', last_name='Manager',
            email='mgr002@test.co', gender='M', department=self.dept, designation=self.desg,
            date_of_joining=date(2020, 1, 1), probation_status='CONFIRMED',
        )

    def test_set_fallback_manager(self):
        """Admin sets a fallback approver for when manager is on leave."""
        result = execute_tool('set_fallback_manager', {
            'employee_id': 'EMP-001',
            'primary_manager_id': 'MGR-001',
            'fallback_manager_id': 'MGR-002',
            'reason': 'manager vacation',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)
        self.assertTrue(FallbackManager.objects.filter(
            employee=self.emp,
            primary_manager=self.manager,
            fallback_manager=self.alt_mgr,
        ).exists())

    def test_set_fallback_with_dates(self):
        """Admin sets a fallback manager with effective date range."""
        result = execute_tool('set_fallback_manager', {
            'employee_id': 'EMP-001',
            'primary_manager_id': 'MGR-001',
            'fallback_manager_id': 'MGR-002',
            'effective_from': date.today().isoformat(),
            'effective_to': (date.today() + timedelta(days=14)).isoformat(),
            'reason': 'planned leave',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertNotIn('error', result)


class TestAdminGetAllRequests(TestCase):
    """Test get_all_requests tool."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        self.sl = _make_sl()
        LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.sl, year=_year(), entitled=Decimal('8.0'),
        )

    def test_get_all_requests(self):
        """get_all_requests returns all leave requests."""
        yesterday = _prev_weekday(1)
        execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'all requests test',
        }, _ctx('EMP-001'))
        result = execute_tool('get_all_requests', {}, _ctx('HR-001', 'ADMIN'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)

    def test_get_all_requests_filter_by_status(self):
        """get_all_requests filters by status."""
        result = execute_tool('get_all_requests', {
            'status': 'APPROVED',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertIn('results', result)

    def test_get_all_requests_filter_by_employee(self):
        """get_all_requests filters by employee_id."""
        yesterday = _prev_weekday(1)
        execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'filter by emp',
        }, _ctx('EMP-001'))
        result = execute_tool('get_all_requests', {
            'employee_id': 'EMP-001',
        }, _ctx('HR-001', 'ADMIN'))
        self.assertIn('results', result)
        self.assertGreater(len(result['results']), 0)


# ====================================================================
# 5. RESPONSE FORMAT TESTS
# ====================================================================

class TestResponseFormat(TestCase):
    """Verify serialization produces clean, readable output."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()
        self.sl = _make_sl()
        self.balance = LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.sl, year=_year(), entitled=Decimal('8.0'),
        )

    def test_balance_has_leave_type_code(self):
        """Balance response includes 'leave_type_code', not raw leave_type_id."""
        result = execute_tool('get_my_balance', {}, _ctx('EMP-001'))
        entry = result['results'][0]
        self.assertIn('leave_type_code', entry)
        self.assertNotIn('leave_type_id', entry)

    def test_balance_has_leave_type_name(self):
        """Balance response includes 'leave_type_name'."""
        result = execute_tool('get_my_balance', {}, _ctx('EMP-001'))
        entry = result['results'][0]
        self.assertIn('leave_type_name', entry)

    def test_balance_has_available_string(self):
        """Balance response includes 'available' as a string."""
        result = execute_tool('get_my_balance', {}, _ctx('EMP-001'))
        entry = result['results'][0]
        self.assertIn('available', entry)
        self.assertIsInstance(entry['available'], str)

    def test_request_has_employee_code_and_name(self):
        """Leave request response includes employee_code and employee_name."""
        yesterday = _prev_weekday(1)
        apply_result = execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'format test',
        }, _ctx('EMP-001'))
        # Fetch via get_all_requests to get the enriched serialization
        result = execute_tool('get_all_requests', {
            'employee_id': 'EMP-001',
        }, _ctx('HR-001', 'ADMIN'))
        entry = result['results'][0]
        self.assertIn('employee_code', entry)
        self.assertIn('employee_name', entry)

    def test_request_has_leave_type_code_not_id(self):
        """Leave request response includes leave_type_code, drops leave_type_id."""
        yesterday = _prev_weekday(1)
        execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'type code test',
        }, _ctx('EMP-001'))
        result = execute_tool('get_all_requests', {
            'employee_id': 'EMP-001',
        }, _ctx('HR-001', 'ADMIN'))
        entry = result['results'][0]
        self.assertIn('leave_type_code', entry)
        self.assertNotIn('leave_type_id', entry)

    def test_none_result_format(self):
        """When handler returns None, serializer returns {'result': None}."""
        from mcp_server.executor import _serialize_result
        self.assertEqual(_serialize_result(None), {"result": None})

    def test_string_result_format(self):
        """When handler returns a plain string, serializer wraps it."""
        from mcp_server.executor import _serialize_result
        self.assertEqual(_serialize_result("hello"), {"result": "hello"})


# ====================================================================
# 6. ERROR HANDLING TESTS
# ====================================================================

class TestErrorHandling(TestCase):
    """Test error cases in execute_tool."""

    def setUp(self):
        self.dept, self.desg, self.manager, self.emp, self.hr = _setup_base()

    def test_unknown_tool_name(self):
        """Unknown tool name returns an error dict."""
        result = execute_tool('totally_fake_tool', {}, _ctx('EMP-001'))
        self.assertIn('error', result)
        self.assertIn('Unknown tool', result['error'])

    def test_invalid_employee_in_context(self):
        """Invalid employee_id in user_context returns an error."""
        result = execute_tool('get_my_balance', {}, _ctx('NONEXISTENT-999'))
        self.assertIn('error', result)
        self.assertIn('Employee not found', result['error'])

    def test_handler_raises_value_error(self):
        """When the underlying handler raises ValueError, it's returned as error."""
        self.sl = _make_sl()
        LeaveBalance.objects.create(
            employee=self.emp, leave_type=self.sl, year=_year(), entitled=Decimal('0.0'),
        )
        yesterday = _prev_weekday(1)
        result = execute_tool('apply_leave', {
            'leave_type': 'SL',
            'start_date': yesterday.isoformat(),
            'end_date': yesterday.isoformat(),
            'reason': 'should fail on balance',
        }, _ctx('EMP-001'))
        self.assertIn('error', result)

    def test_approve_nonexistent_request(self):
        """Approving a non-existent request returns an error."""
        result = execute_tool('approve_leave', {
            'request_id': 999999,
        }, _ctx('MGR-001', 'MANAGER'))
        self.assertIn('error', result)

    def test_reject_nonexistent_request(self):
        """Rejecting a non-existent request returns an error."""
        result = execute_tool('reject_leave', {
            'request_id': 999999,
            'remarks': 'does not exist',
        }, _ctx('MGR-001', 'MANAGER'))
        self.assertIn('error', result)
