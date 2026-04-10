from rest_framework import serializers
from employees.models import Department, Team, Designation, Employee, EmployeeChangeLog, PendingHRAction, OnboardingTemplate


class DepartmentSerializer(serializers.ModelSerializer):
    employee_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Department
        fields = '__all__'


class TeamSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Team
        fields = '__all__'


class DesignationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Designation
        fields = '__all__'


class EmployeeListSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)
    designation_title = serializers.CharField(source='designation.title', read_only=True)
    manager_name = serializers.CharField(source='reporting_manager.full_name', read_only=True, default=None)

    class Meta:
        model = Employee
        fields = ['employee_id', 'full_name', 'email', 'department_name',
                  'designation_title', 'manager_name', 'employment_type',
                  'probation_status', 'is_active', 'date_of_joining']


class EmployeeDetailSerializer(serializers.ModelSerializer):
    department = DepartmentSerializer(read_only=True)
    designation = DesignationSerializer(read_only=True)
    teams = TeamSerializer(many=True, read_only=True)
    reporting_manager = EmployeeListSerializer(read_only=True)

    class Meta:
        model = Employee
        fields = '__all__'


class EmployeeWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = '__all__'


class PendingHRActionSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)

    class Meta:
        model = PendingHRAction
        fields = '__all__'
