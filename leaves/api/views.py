from datetime import date
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from employees.models import Employee
from leaves.models import (
    LeaveType, LeaveRequest, LeaveBalance, EmployeeOverride,
    OptionalHoliday, OptionalHolidaySelection, FallbackManager,
    LeavePolicyVersion,
)
from leaves.services import (
    apply_leave, cancel_leave, validate_leave as validate_leave_svc,
    approve_leave, reject_leave, adjust_balance, get_balances,
    create_leave_type, update_leave_type, deactivate_leave_type,
    create_override, remove_override, get_overrides,
    bulk_create_overrides, confirm_batch, rollback_batch,
    run_monthly_accrual, run_bulk_credit, run_year_end_processing,
)
from .serializers import (
    LeaveTypeSerializer, LeaveRequestSerializer, LeaveBalanceSerializer,
    EmployeeOverrideSerializer, OptionalHolidaySerializer,
    OptionalHolidaySelectionSerializer, FallbackManagerSerializer,
    LeavePolicyVersionSerializer, BatchOperationSerializer,
)


def _get_actor(request):
    emp_id = request.headers.get('X-Employee-Id') or request.query_params.get('actor')
    if emp_id:
        try:
            return Employee.objects.get(employee_id=emp_id)
        except Employee.DoesNotExist:
            pass
    return None


def _parse_date(s):
    if not s:
        return None
    return date.fromisoformat(s)


# ── Employee Leave Tools ──

@api_view(['POST'])
def apply_leave_view(request):
    actor = _get_actor(request)
    if not actor:
        return Response({'error': 'Employee not identified'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        req = apply_leave(
            employee=actor,
            leave_type_code=request.data['leave_type'],
            start_date=_parse_date(request.data['start_date']),
            end_date=_parse_date(request.data['end_date']),
            reason=request.data.get('reason', ''),
            is_half_day=request.data.get('is_half_day', False),
            half_day_period=request.data.get('half_day_period'),
            idempotency_key=request.data.get('idempotency_key'),
        )
        if isinstance(req, dict):
            return Response(req)
        return Response(LeaveRequestSerializer(req).data, status=status.HTTP_201_CREATED)
    except (ValueError, Exception) as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def cancel_leave_view(request, pk):
    actor = _get_actor(request)
    if not actor:
        return Response({'error': 'Employee not identified'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        req = cancel_leave(actor, pk, request.data.get('reason'))
        return Response(LeaveRequestSerializer(req).data)
    except (ValueError, Exception) as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def validate_leave_view(request):
    actor = _get_actor(request)
    if not actor:
        return Response({'error': 'Employee not identified'}, status=status.HTTP_400_BAD_REQUEST)
    passed, error = validate_leave_svc(
        actor,
        request.data['leave_type'],
        _parse_date(request.data['start_date']),
        _parse_date(request.data['end_date']),
        request.data.get('is_half_day', False),
        request.data.get('half_day_period'),
    )
    return Response({'valid': passed, 'error': error})


@api_view(['GET'])
def my_balance(request):
    actor = _get_actor(request)
    if not actor:
        return Response({'error': 'Employee not identified'}, status=status.HTTP_400_BAD_REQUEST)
    balances = get_balances(actor.employee_id, year=request.query_params.get('year'))
    return Response(LeaveBalanceSerializer(balances, many=True).data)


@api_view(['GET'])
def my_requests(request):
    actor = _get_actor(request)
    if not actor:
        return Response({'error': 'Employee not identified'}, status=status.HTTP_400_BAD_REQUEST)
    qs = LeaveRequest.objects.filter(employee=actor).select_related('leave_type', 'current_approver')
    req_status = request.query_params.get('status')
    if req_status:
        qs = qs.filter(status=req_status)
    return Response(LeaveRequestSerializer(qs.order_by('-applied_at'), many=True).data)


@api_view(['GET'])
def leave_policy(request):
    types = LeaveType.objects.filter(is_active=True)
    return Response(LeaveTypeSerializer(types, many=True).data)


# ── Manager Tools ──

@api_view(['GET'])
def team_requests(request):
    actor = _get_actor(request)
    if not actor:
        return Response({'error': 'Employee not identified'}, status=status.HTTP_400_BAD_REQUEST)
    direct_reports = Employee.objects.filter(reporting_manager=actor, is_active=True)
    qs = LeaveRequest.objects.filter(employee__in=direct_reports).select_related('employee', 'leave_type')
    req_status = request.query_params.get('status')
    if req_status:
        qs = qs.filter(status=req_status)
    return Response(LeaveRequestSerializer(qs.order_by('-applied_at'), many=True).data)


@api_view(['POST'])
def approve_leave_view(request, pk):
    actor = _get_actor(request)
    if not actor:
        return Response({'error': 'Employee not identified'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        req = approve_leave(actor, pk, request.data.get('remarks', ''))
        return Response(LeaveRequestSerializer(req).data)
    except (ValueError, Exception) as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def reject_leave_view(request, pk):
    actor = _get_actor(request)
    if not actor:
        return Response({'error': 'Employee not identified'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        req = reject_leave(actor, pk, request.data.get('remarks', ''))
        return Response(LeaveRequestSerializer(req).data)
    except (ValueError, Exception) as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def team_balance(request):
    actor = _get_actor(request)
    if not actor:
        return Response({'error': 'Employee not identified'}, status=status.HTTP_400_BAD_REQUEST)
    direct_reports = Employee.objects.filter(reporting_manager=actor, is_active=True)
    balances = LeaveBalance.objects.filter(employee__in=direct_reports).select_related('employee', 'leave_type')
    return Response(LeaveBalanceSerializer(balances, many=True).data)


# ── Admin Tools ──

@api_view(['POST'])
def create_leave_type_view(request):
    actor = _get_actor(request)
    try:
        lt = create_leave_type(actor, request.data)
        return Response(LeaveTypeSerializer(lt).data, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT'])
def update_leave_type_view(request, code):
    actor = _get_actor(request)
    try:
        lt = update_leave_type(
            actor, code,
            request.data.get('changes', {}),
            request.data.get('change_summary', ''),
            request.data.get('effective_mode', 'PROSPECTIVE'),
        )
        return Response(LeaveTypeSerializer(lt).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def create_override_view(request):
    actor = _get_actor(request)
    try:
        data = dict(request.data)
        employee_id = data.pop('employee_id')
        leave_type_code = data.pop('leave_type_code', None)
        override = create_override(actor, employee_id, leave_type_code, **data)
        return Response(EmployeeOverrideSerializer(override).data, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def remove_override_view(request, pk):
    actor = _get_actor(request)
    try:
        override = remove_override(actor, pk, request.data.get('reason'))
        return Response(EmployeeOverrideSerializer(override).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def get_overrides_view(request):
    overrides = get_overrides(
        employee_id=request.query_params.get('employee_id'),
        leave_type_code=request.query_params.get('leave_type'),
    )
    return Response(EmployeeOverrideSerializer(overrides, many=True).data)


@api_view(['POST'])
def adjust_balance_view(request):
    actor = _get_actor(request)
    try:
        balance = adjust_balance(
            actor, request.data['employee_id'], request.data['leave_type'],
            request.data['days'], request.data.get('reason', ''),
        )
        return Response(LeaveBalanceSerializer(balance).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def bulk_overrides_view(request):
    actor = _get_actor(request)
    try:
        batch = bulk_create_overrides(
            actor, request.data['filter_criteria'], request.data['override_template'],
        )
        return Response(BatchOperationSerializer(batch).data, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def confirm_batch_view(request, pk):
    actor = _get_actor(request)
    try:
        batch = confirm_batch(actor, pk)
        return Response(BatchOperationSerializer(batch).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def rollback_batch_view(request, pk):
    actor = _get_actor(request)
    try:
        batch = rollback_batch(actor, pk, request.data.get('reason', ''))
        return Response(BatchOperationSerializer(batch).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def set_fallback_manager_view(request):
    try:
        fm = FallbackManager.objects.create(
            employee=Employee.objects.get(employee_id=request.data['employee_id']),
            primary_manager=Employee.objects.get(employee_id=request.data['primary_manager_id']),
            fallback_manager=Employee.objects.get(employee_id=request.data['fallback_manager_id']),
            effective_from=_parse_date(request.data.get('effective_from', str(date.today()))),
            effective_to=_parse_date(request.data.get('effective_to')),
            reason=request.data.get('reason', ''),
            created_by=_get_actor(request),
        )
        return Response(FallbackManagerSerializer(fm).data, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def policy_versions(request, code):
    versions = LeavePolicyVersion.objects.filter(leave_type__code=code)
    return Response(LeavePolicyVersionSerializer(versions, many=True).data)


@api_view(['POST'])
def trigger_bulk_credit_view(request):
    try:
        results = run_bulk_credit(int(request.data.get('year', date.today().year)), request.data.get('leave_type'))
        return Response({'results': results, 'count': len(results)})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def trigger_monthly_accrual_view(request):
    try:
        results = run_monthly_accrual(_parse_date(request.data.get('date')))
        return Response({'results': results, 'count': len(results)})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def trigger_year_end_view(request):
    try:
        results = run_year_end_processing(
            int(request.data.get('year', date.today().year - 1)),
            request.data.get('dry_run', False),
        )
        return Response({'results': results, 'count': len(results)})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def all_requests(request):
    qs = LeaveRequest.objects.all().select_related('employee', 'leave_type', 'current_approver')
    req_status = request.query_params.get('status')
    if req_status:
        qs = qs.filter(status=req_status)
    emp_id = request.query_params.get('employee_id')
    if emp_id:
        qs = qs.filter(employee__employee_id=emp_id)
    return Response(LeaveRequestSerializer(qs.order_by('-applied_at'), many=True).data)


# ── Optional Holidays ──

@api_view(['POST', 'GET'])
def optional_holidays(request):
    if request.method == 'POST':
        actor = _get_actor(request)
        try:
            oh = OptionalHoliday.objects.create(
                name=request.data['name'],
                date=_parse_date(request.data['date']),
                year=request.data.get('year', date.today().year),
                description=request.data.get('description', ''),
                created_by=actor,
            )
            return Response(OptionalHolidaySerializer(oh).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    else:
        year = request.query_params.get('year', date.today().year)
        holidays = OptionalHoliday.objects.filter(year=year, is_active=True)
        return Response(OptionalHolidaySerializer(holidays, many=True).data)


@api_view(['POST'])
def select_optional_holiday_view(request):
    actor = _get_actor(request)
    if not actor:
        return Response({'error': 'Employee not identified'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        holiday = OptionalHoliday.objects.get(id=request.data['holiday_id'])
        sel, created = OptionalHolidaySelection.objects.get_or_create(
            employee=actor, holiday=holiday,
            defaults={'status': 'PENDING'}
        )
        if not created:
            return Response({'error': 'Already selected'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OptionalHolidaySelectionSerializer(sel).data, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
