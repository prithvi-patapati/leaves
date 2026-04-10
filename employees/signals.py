import django.dispatch

employee_created = django.dispatch.Signal()
employee_updated = django.dispatch.Signal()
employee_confirmed = django.dispatch.Signal()
employee_deactivated = django.dispatch.Signal()
employee_transferred = django.dispatch.Signal()
team_membership_changed = django.dispatch.Signal()
