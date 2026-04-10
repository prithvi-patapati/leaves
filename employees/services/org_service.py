from django.db import transaction
from employees.models import Department, Team
from employees import signals


def create_department(name, code, description='', head=None):
    return Department.objects.create(name=name, code=code, description=description, head=head)


def update_department(code, **changes):
    dept = Department.objects.get(code=code)
    for field, value in changes.items():
        setattr(dept, field, value)
    dept.save()
    return dept


def list_departments(active_only=True):
    qs = Department.objects.all()
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.annotate(employee_count=models_Count('employees')).order_by('name')


def create_team(name, code, description='', lead=None):
    return Team.objects.create(name=name, code=code, description=description, lead=lead)


def update_team(code, **changes):
    team = Team.objects.get(code=code)
    for field, value in changes.items():
        setattr(team, field, value)
    team.save()
    return team


def list_teams(active_only=True):
    qs = Team.objects.all()
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.annotate(member_count=models_Count('members')).order_by('name')


@transaction.atomic
def add_to_team(employee_id, team_code):
    from employees.models import Employee
    employee = Employee.objects.get(employee_id=employee_id)
    team = Team.objects.get(code=team_code)
    team.members.add(employee)

    signals.team_membership_changed.send(
        sender=Team,
        team_code=team_code,
        employee_id=employee_id,
        action='ADDED',
    )
    return team


@transaction.atomic
def remove_from_team(employee_id, team_code):
    from employees.models import Employee
    employee = Employee.objects.get(employee_id=employee_id)
    team = Team.objects.get(code=team_code)
    team.members.remove(employee)

    signals.team_membership_changed.send(
        sender=Team,
        team_code=team_code,
        employee_id=employee_id,
        action='REMOVED',
    )
    return team


# Helper to avoid circular import
from django.db.models import Count as models_Count
