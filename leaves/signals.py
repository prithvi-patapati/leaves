import django.dispatch

leave_applied = django.dispatch.Signal()
leave_approved = django.dispatch.Signal()
leave_rejected = django.dispatch.Signal()
leave_cancelled = django.dispatch.Signal()
policy_changed = django.dispatch.Signal()
balance_adjusted = django.dispatch.Signal()
lop_approved = django.dispatch.Signal()
