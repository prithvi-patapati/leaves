from django.urls import path
from . import views

urlpatterns = [
    # Employee CRUD
    path('', views.search_employees, name='search_employees'),
    path('create/', views.add_employee, name='add_employee'),
    path('<str:employee_id>/', views.get_employee, name='get_employee'),
    path('<str:employee_id>/update/', views.update_employee, name='update_employee'),
    path('<str:employee_id>/confirm/', views.confirm_employee, name='confirm_employee'),
    path('<str:employee_id>/deactivate/', views.deactivate_employee, name='deactivate_employee'),
    path('<str:employee_id>/transfer/', views.transfer_employee, name='transfer_employee'),

    # Departments
    path('departments/', views.departments, name='departments'),
    path('departments/<str:code>/', views.update_department, name='update_department'),

    # Teams
    path('teams/', views.teams, name='teams'),
    path('teams/<str:code>/', views.update_team, name='update_team'),
    path('teams/<str:code>/members/', views.add_to_team, name='add_to_team'),
    path('teams/<str:code>/members/remove/', views.remove_from_team, name='remove_from_team'),

    # HR Actions
    path('hr-actions/', views.hr_actions, name='hr_actions'),
    path('hr-actions/<int:pk>/resolve/', views.resolve_hr_action, name='resolve_hr_action'),
    path('hr-actions/<int:pk>/execute/', views.execute_hr_action, name='execute_hr_action'),
]
