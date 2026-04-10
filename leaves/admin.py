from django.contrib import admin
from .models import (
    LeaveType, LeavePolicyVersion, EmployeeOverride, LeaveBalance,
    LeaveBalanceLedger, LeaveRequest, OptionalHoliday, OptionalHolidaySelection,
    CompanyConfig, FallbackManager, BatchOperation, IdempotencyLog, PayrollAdjustmentPending,
)


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'entitlement_days', 'credit_method', 'is_active']
    list_filter = ['credit_method', 'is_active']
    search_fields = ['code', 'name']


@admin.register(LeavePolicyVersion)
class LeavePolicyVersionAdmin(admin.ModelAdmin):
    list_display = ['leave_type', 'version', 'effective_mode', 'changed_at']
    list_filter = ['effective_mode']


@admin.register(EmployeeOverride)
class EmployeeOverrideAdmin(admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'is_active', 'effective_from', 'effective_to']
    list_filter = ['is_active', 'leave_type']


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'year', 'entitled', 'used', 'pending']
    list_filter = ['year', 'leave_type']


@admin.register(LeaveBalanceLedger)
class LeaveBalanceLedgerAdmin(admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'txn_type', 'days', 'created_at']
    list_filter = ['txn_type', 'year']


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'start_date', 'end_date', 'status', 'applied_at']
    list_filter = ['status', 'leave_type']
    search_fields = ['employee__full_name', 'employee__employee_id']


@admin.register(OptionalHoliday)
class OptionalHolidayAdmin(admin.ModelAdmin):
    list_display = ['name', 'date', 'year', 'is_active']
    list_filter = ['year', 'is_active']


@admin.register(OptionalHolidaySelection)
class OptionalHolidaySelectionAdmin(admin.ModelAdmin):
    list_display = ['employee', 'holiday', 'status']
    list_filter = ['status']


@admin.register(CompanyConfig)
class CompanyConfigAdmin(admin.ModelAdmin):
    list_display = ['leave_year_start_month', 'working_days_per_week']


@admin.register(FallbackManager)
class FallbackManagerAdmin(admin.ModelAdmin):
    list_display = ['employee', 'primary_manager', 'fallback_manager', 'is_active']
    list_filter = ['is_active']


@admin.register(BatchOperation)
class BatchOperationAdmin(admin.ModelAdmin):
    list_display = ['action_type', 'status', 'affected_count', 'created_at']
    list_filter = ['status', 'action_type']


@admin.register(IdempotencyLog)
class IdempotencyLogAdmin(admin.ModelAdmin):
    list_display = ['key', 'action', 'status', 'created_at']


@admin.register(PayrollAdjustmentPending)
class PayrollAdjustmentPendingAdmin(admin.ModelAdmin):
    list_display = ['employee', 'adjustment_type', 'is_processed', 'created_at']
    list_filter = ['adjustment_type', 'is_processed']
