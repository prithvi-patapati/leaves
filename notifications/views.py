import os
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from .models import Activity


def activity_page(request):
    """Serve the activity feed HTML page."""
    template_path = os.path.join(os.path.dirname(__file__), 'templates', 'activity.html')
    with open(template_path, 'r') as f:
        return HttpResponse(f.read())


def api_activity_feed(request):
    """Return activity feed filtered by role.

    Query params:
    - view: 'hr' | 'manager' | 'employee'
    - employee_id: filter for specific employee (manager/employee view)
    - manager_id: filter for manager's team
    - event_type: filter by event type
    - limit: max results (default 50)
    """
    view = request.GET.get('view', 'hr')
    employee_id = request.GET.get('employee_id', '')
    manager_id = request.GET.get('manager_id', '')
    event_type = request.GET.get('event_type', '')
    limit = int(request.GET.get('limit', 50))

    qs = Activity.objects.all()

    if view == 'employee' and employee_id:
        # Employee sees only their own activity
        qs = qs.filter(target_id=employee_id)

    elif view == 'manager' and manager_id:
        # Manager sees their team's activity
        qs = qs.filter(
            Q(manager_id=manager_id) |
            Q(actor_id=manager_id) |
            Q(visibility__in=['ALL', 'MANAGER'])
        )

    # HR sees everything (no filter)

    if event_type:
        qs = qs.filter(event_type=event_type)

    activities = qs[:limit]

    data = [{
        'id': a.id,
        'event_type': a.event_type,
        'title': a.title,
        'description': a.description,
        'actor_id': a.actor_id,
        'actor_name': a.actor_name,
        'target_id': a.target_id,
        'target_name': a.target_name,
        'visibility': a.visibility,
        'metadata': a.metadata,
        'channels': a.channels,
        'created_at': a.created_at.isoformat(),
    } for a in activities]

    return JsonResponse({'activities': data, 'count': len(data)})


def api_activity_stats(request):
    """Quick stats for the activity feed."""
    from django.db.models import Count
    from django.utils import timezone
    from datetime import timedelta

    today = timezone.now().date()
    week_ago = today - timedelta(days=7)

    stats = {
        'today': Activity.objects.filter(created_at__date=today).count(),
        'this_week': Activity.objects.filter(created_at__date__gte=week_ago).count(),
        'pending_approvals': 0,
    }

    # Count pending approvals from LeaveRequest
    try:
        from leaves.models import LeaveRequest
        stats['pending_approvals'] = LeaveRequest.objects.filter(status='PENDING').count()
    except ImportError:
        pass

    return JsonResponse(stats)
