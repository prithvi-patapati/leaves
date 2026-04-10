from rest_framework import serializers
from leaves.models import (
    LeaveType, LeaveRequest, LeaveBalance, LeaveBalanceLedger,
    EmployeeOverride, LeavePolicyVersion, OptionalHoliday,
    OptionalHolidaySelection, FallbackManager, BatchOperation, CompanyConfig,
)


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = '__all__'


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    leave_type_code = serializers.CharField(source='leave_type.code', read_only=True)
    leave_type_name = serializers.CharField(source='leave_type.name', read_only=True)
    approver_name = serializers.CharField(source='current_approver.full_name', read_only=True, default=None)

    class Meta:
        model = LeaveRequest
        fields = '__all__'


class LeaveBalanceSerializer(serializers.ModelSerializer):
    leave_type_code = serializers.CharField(source='leave_type.code', read_only=True)
    leave_type_name = serializers.CharField(source='leave_type.name', read_only=True)
    available = serializers.DecimalField(max_digits=6, decimal_places=1, read_only=True)

    class Meta:
        model = LeaveBalance
        fields = '__all__'


class LeaveBalanceLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveBalanceLedger
        fields = '__all__'


class EmployeeOverrideSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    leave_type_code = serializers.CharField(source='leave_type.code', read_only=True, default='ALL')

    class Meta:
        model = EmployeeOverride
        fields = '__all__'


class OptionalHolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = OptionalHoliday
        fields = '__all__'


class OptionalHolidaySelectionSerializer(serializers.ModelSerializer):
    holiday_name = serializers.CharField(source='holiday.name', read_only=True)

    class Meta:
        model = OptionalHolidaySelection
        fields = '__all__'


class FallbackManagerSerializer(serializers.ModelSerializer):
    class Meta:
        model = FallbackManager
        fields = '__all__'


class BatchOperationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchOperation
        fields = '__all__'


class LeavePolicyVersionSerializer(serializers.ModelSerializer):
    leave_type_code = serializers.CharField(source='leave_type.code', read_only=True)

    class Meta:
        model = LeavePolicyVersion
        fields = '__all__'
