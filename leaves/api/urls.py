from django.urls import path
from . import views

urlpatterns = [
    # Employee leave tools
    path('apply/', views.apply_leave_view, name='apply_leave'),
    path('validate/', views.validate_leave_view, name='validate_leave'),
    path('my-balance/', views.my_balance, name='my_balance'),
    path('my-requests/', views.my_requests, name='my_requests'),
    path('policy/', views.leave_policy, name='leave_policy'),
    path('requests/<int:pk>/cancel/', views.cancel_leave_view, name='cancel_leave'),

    # Manager tools
    path('team-requests/', views.team_requests, name='team_requests'),
    path('team-balance/', views.team_balance, name='team_balance'),
    path('requests/<int:pk>/approve/', views.approve_leave_view, name='approve_leave'),
    path('requests/<int:pk>/reject/', views.reject_leave_view, name='reject_leave'),

    # Admin tools
    path('types/create/', views.create_leave_type_view, name='create_leave_type'),
    path('types/<str:code>/update/', views.update_leave_type_view, name='update_leave_type'),
    path('types/<str:code>/versions/', views.policy_versions, name='policy_versions'),

    path('overrides/', views.get_overrides_view, name='get_overrides'),
    path('overrides/create/', views.create_override_view, name='create_override'),
    path('overrides/<int:pk>/remove/', views.remove_override_view, name='remove_override'),

    path('balance/adjust/', views.adjust_balance_view, name='adjust_balance'),
    path('batch/create/', views.bulk_overrides_view, name='bulk_overrides'),
    path('batch/<int:pk>/confirm/', views.confirm_batch_view, name='confirm_batch'),
    path('batch/<int:pk>/rollback/', views.rollback_batch_view, name='rollback_batch'),

    path('fallback-manager/', views.set_fallback_manager_view, name='set_fallback_manager'),
    path('requests/', views.all_requests, name='all_requests'),

    # Engine triggers
    path('engine/bulk-credit/', views.trigger_bulk_credit_view, name='trigger_bulk_credit'),
    path('engine/monthly-accrual/', views.trigger_monthly_accrual_view, name='trigger_monthly_accrual'),
    path('engine/year-end/', views.trigger_year_end_view, name='trigger_year_end'),

    # Optional holidays
    path('optional-holidays/', views.optional_holidays, name='optional_holidays'),
    path('optional-holidays/select/', views.select_optional_holiday_view, name='select_optional_holiday'),
]
