import os
import json
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count
from employees.models import Employee
from leaves.models import LeaveRequest


def _serialize_date(d):
    return d.isoformat() if d else None


# ── Pages ──

def approve_page(request):
    template_path = os.path.join(os.path.dirname(__file__), 'templates', 'approve.html')
    with open(template_path, 'r') as f:
        html = f.read()
    return HttpResponse(html)


# ── APIs ──

def api_managers(request):
    managers = Employee.objects.filter(
        is_active=True,
        direct_reports__is_active=True,
    ).annotate(
        report_count=Count('direct_reports')
    ).filter(report_count__gt=0).order_by('-report_count')

    data = []
    for m in managers:
        data.append({
            'employee_id': m.employee_id,
            'full_name': m.full_name,
            'designation': m.designation.title if m.designation else '',
            'report_count': m.report_count,
        })
    return JsonResponse({'managers': data})


def api_pending_for_manager(request, manager_id):
    pending = LeaveRequest.objects.filter(
        status='PENDING',
        current_approver__employee_id=manager_id,
    ).select_related('employee', 'leave_type', 'current_approver').order_by('-applied_at')

    data = []
    for r in pending:
        data.append({
            'id': r.id,
            'employee': r.employee.full_name,
            'employee_id': r.employee.employee_id,
            'leave_type': r.leave_type.name,
            'leave_type_code': r.leave_type.code,
            'start_date': _serialize_date(r.start_date),
            'end_date': _serialize_date(r.end_date),
            'duration_days': str(r.duration_days),
            'is_half_day': r.is_half_day,
            'half_day_period': r.half_day_period,
            'reason': r.reason,
            'applied_at': r.applied_at.isoformat() if r.applied_at else None,
        })
    return JsonResponse({'pending': data, 'count': len(data)})


@csrf_exempt
def api_approve(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        body = {}

    remarks = body.get('remarks', 'Approved via manager screen')
    approver_id = body.get('approver_id')

    try:
        lr = LeaveRequest.objects.select_related('employee', 'leave_type', 'current_approver').get(pk=pk)
    except LeaveRequest.DoesNotExist:
        return JsonResponse({'error': 'Request not found'}, status=404)

    if approver_id:
        try:
            approver = Employee.objects.get(employee_id=approver_id)
        except Employee.DoesNotExist:
            return JsonResponse({'error': f'Approver {approver_id} not found'}, status=404)
    else:
        approver = lr.current_approver

    if not approver:
        return JsonResponse({'error': 'No approver set'}, status=400)

    from leaves.services.leave_approval import approve_leave
    try:
        result = approve_leave(approver, lr.id, remarks=remarks)
        return JsonResponse({
            'status': result.status,
            'employee': result.employee.full_name,
            'leave_type': result.leave_type.name,
            'message': f"Approved {result.employee.full_name}'s {result.leave_type.name}",
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
def api_reject(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        body = {}

    remarks = body.get('remarks', '')
    approver_id = body.get('approver_id')

    if not remarks:
        return JsonResponse({'error': 'Remarks required for rejection'}, status=400)

    try:
        lr = LeaveRequest.objects.select_related('employee', 'leave_type', 'current_approver').get(pk=pk)
    except LeaveRequest.DoesNotExist:
        return JsonResponse({'error': 'Request not found'}, status=404)

    if approver_id:
        try:
            approver = Employee.objects.get(employee_id=approver_id)
        except Employee.DoesNotExist:
            return JsonResponse({'error': f'Approver {approver_id} not found'}, status=404)
    else:
        approver = lr.current_approver

    if not approver:
        return JsonResponse({'error': 'No approver set'}, status=400)

    from leaves.services.leave_approval import reject_leave
    try:
        result = reject_leave(approver, lr.id, remarks=remarks)
        return JsonResponse({
            'status': result.status,
            'employee': result.employee.full_name,
            'leave_type': result.leave_type.name,
            'message': f"Rejected {result.employee.full_name}'s {result.leave_type.name}",
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
