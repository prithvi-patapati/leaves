from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path('approve/', views.approve_page, name='approve-page'),

    # APIs
    path('api/managers/', views.api_managers, name='dashboard-api-managers'),
    path('api/pending/<str:manager_id>/', views.api_pending_for_manager, name='dashboard-api-pending-manager'),
    path('api/requests/<int:pk>/approve/', views.api_approve, name='dashboard-api-approve'),
    path('api/requests/<int:pk>/reject/', views.api_reject, name='dashboard-api-reject'),
]
