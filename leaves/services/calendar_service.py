from datetime import date
from leaves.models import LeaveRequest
from employees.models import Employee


def get_team_calendar(actor, start_date, end_date):
    reports = Employee.objects.filter(reporting_manager=actor, is_active=True)
    requests = LeaveRequest.objects.filter(
        employee__in=reports,
        status='APPROVED',
        start_date__lte=end_date,
        end_date__gte=start_date,
    ).select_related('employee', 'leave_type')
    return requests
