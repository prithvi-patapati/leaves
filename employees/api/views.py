from datetime import date
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from employees.models import Employee, Department, Team
from employees.services import employee_service, org_service
from .serializers import (
    EmployeeDetailSerializer, EmployeeListSerializer, EmployeeWriteSerializer,
    DepartmentSerializer, TeamSerializer, PendingHRActionSerializer,
)


def _get_actor(request):
    emp_id = request.headers.get('X-Employee-Id') or request.query_params.get('actor')
    if emp_id:
        try:
            return Employee.objects.get(employee_id=emp_id)
        except Employee.DoesNotExist:
            pass
    return None


# ── Employee CRUD ──

@api_view(['POST'])
def add_employee(request):
    serializer = EmployeeWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    actor = _get_actor(request)
    try:
        emp, summary = employee_service.add_employee(actor=actor, **serializer.validated_data)
        return Response({
            'employee': EmployeeDetailSerializer(emp).data,
            'onboarding_summary': summary,
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def get_employee(request, employee_id):
    try:
        emp = employee_service.get_employee(employee_id)
        return Response(EmployeeDetailSerializer(emp).data)
    except Employee.DoesNotExist:
        return Response({'error': 'Employee not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['PUT'])
def update_employee(request, employee_id):
    actor = _get_actor(request)
    try:
        emp = employee_service.update_employee(actor, employee_id, **request.data)
        return Response(EmployeeDetailSerializer(emp).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def confirm_employee(request, employee_id):
    actor = _get_actor(request)
    try:
        emp = employee_service.confirm_employee(actor, employee_id)
        return Response(EmployeeDetailSerializer(emp).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def deactivate_employee(request, employee_id):
    actor = _get_actor(request)
    try:
        emp = employee_service.deactivate_employee(
            actor, employee_id,
            request.data.get('last_working_date', str(date.today())),
            request.data.get('exit_reason', 'RESIGNED'),
        )
        return Response(EmployeeDetailSerializer(emp).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def transfer_employee(request, employee_id):
    actor = _get_actor(request)
    kwargs = {}
    if 'department_code' in request.data:
        kwargs['department'] = Department.objects.get(code=request.data['department_code'])
    if 'reporting_manager_id' in request.data:
        kwargs['reporting_manager'] = Employee.objects.get(employee_id=request.data['reporting_manager_id'])
    try:
        emp = employee_service.transfer_employee(actor, employee_id, **kwargs)
        return Response(EmployeeDetailSerializer(emp).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def search_employees(request):
    employees = employee_service.search_employees(
        department=request.query_params.get('department'),
        team=request.query_params.get('team'),
        designation=request.query_params.get('designation'),
        probation_status=request.query_params.get('probation_status'),
        reporting_manager=request.query_params.get('reporting_manager'),
        name=request.query_params.get('name'),
        is_active=request.query_params.get('is_active', 'true').lower() == 'true',
    )
    return Response(EmployeeListSerializer(employees, many=True).data)


# ── Department & Team ──

@api_view(['POST', 'GET'])
def departments(request):
    if request.method == 'POST':
        try:
            dept = org_service.create_department(**request.data)
            return Response(DepartmentSerializer(dept).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    else:
        from django.db.models import Count
        depts = Department.objects.filter(is_active=True).annotate(employee_count=Count('employees'))
        return Response(DepartmentSerializer(depts, many=True).data)


@api_view(['PUT'])
def update_department(request, code):
    try:
        dept = org_service.update_department(code, **request.data)
        return Response(DepartmentSerializer(dept).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST', 'GET'])
def teams(request):
    if request.method == 'POST':
        try:
            team = org_service.create_team(**request.data)
            return Response(TeamSerializer(team).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    else:
        from django.db.models import Count
        all_teams = Team.objects.filter(is_active=True).annotate(member_count=Count('members'))
        return Response(TeamSerializer(all_teams, many=True).data)


@api_view(['PUT'])
def update_team(request, code):
    try:
        team = org_service.update_team(code, **request.data)
        return Response(TeamSerializer(team).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def add_to_team(request, code):
    try:
        team = org_service.add_to_team(request.data['employee_id'], code)
        return Response(TeamSerializer(team).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
def remove_from_team(request, code):
    try:
        team = org_service.remove_from_team(request.data['employee_id'], code)
        return Response(TeamSerializer(team).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ── HR Actions ──

@api_view(['GET'])
def hr_actions(request):
    from leaves.services.hr_action_service import get_pending
    actions = get_pending(
        status=request.query_params.get('status', 'OPEN'),
        priority=request.query_params.get('priority'),
    )
    return Response(PendingHRActionSerializer(actions, many=True).data)


@api_view(['POST'])
def resolve_hr_action(request, pk):
    from leaves.services.hr_action_service import resolve_action
    actor = _get_actor(request)
    try:
        action = resolve_action(actor, pk, request.data.get('status', 'RESOLVED'), request.data.get('notes', ''))
        return Response(PendingHRActionSerializer(action).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def execute_hr_action(request, pk):
    from leaves.services.hr_action_service import execute_suggested_action
    actor = _get_actor(request)
    try:
        action = execute_suggested_action(actor, pk, request.data.get('suggestion_index', 0))
        return Response(PendingHRActionSerializer(action).data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
