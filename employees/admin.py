from django.contrib import admin
from .models import Department, Team, Designation, Employee, EmployeeChangeLog, OnboardingTemplate, PendingHRAction


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active']
    search_fields = ['name', 'code']
    list_filter = ['is_active']


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active']
    search_fields = ['name', 'code']
    list_filter = ['is_active']


@admin.register(Designation)
class DesignationAdmin(admin.ModelAdmin):
    list_display = ['title', 'level', 'is_active']
    search_fields = ['title']
    list_filter = ['level', 'is_active']


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['employee_id', 'full_name', 'department', 'designation', 'is_active']
    search_fields = ['employee_id', 'full_name', 'email']
    list_filter = ['department', 'is_active', 'employment_type', 'probation_status']


@admin.register(EmployeeChangeLog)
class EmployeeChangeLogAdmin(admin.ModelAdmin):
    list_display = ['employee', 'field_changed', 'changed_via', 'created_at']
    list_filter = ['field_changed', 'changed_via']


@admin.register(OnboardingTemplate)
class OnboardingTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'priority', 'is_active']
    list_filter = ['is_active']


@admin.register(PendingHRAction)
class PendingHRActionAdmin(admin.ModelAdmin):
    list_display = ['title', 'trigger_type', 'status', 'priority', 'created_at']
    list_filter = ['status', 'priority', 'trigger_type']
