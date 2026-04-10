from decimal import Decimal
from leaves.models import LeaveType, LeaveBalance, LeaveBalanceLedger
from employees.models import Employee


def run_year_end_processing(ending_year, dry_run=False):
    new_year = ending_year + 1
    summary = []

    employees = Employee.objects.filter(is_active=True)

    for employee in employees:
        # Step 1: CONVERT types (PL → EL)
        for lt in LeaveType.objects.filter(year_end_action='CONVERT', is_active=True):
            balance = LeaveBalance.objects.filter(
                employee=employee, leave_type=lt, year=ending_year
            ).first()
            if not balance or balance.available <= 0:
                continue

            target_type = lt.convert_to
            if not target_type:
                continue

            convert_days = balance.available

            if not dry_run:
                # Debit from source
                balance.lapsed = Decimal('0')
                balance.save()

                target_balance, _ = LeaveBalance.objects.get_or_create(
                    employee=employee, leave_type=target_type, year=ending_year,
                    defaults={'entitled': Decimal('0')}
                )

                cap = target_type.carry_forward_max
                if cap > 0:
                    room = max(Decimal('0'), Decimal(str(cap)) - target_balance.available)
                    actual_convert = min(convert_days, room)
                else:
                    actual_convert = convert_days
                lapse_remainder = convert_days - actual_convert

                target_balance.converted_in += actual_convert
                target_balance.save()

                LeaveBalanceLedger.objects.create(
                    employee=employee, leave_type=lt, year=ending_year,
                    txn_type='CONVERSION_OUT', days=-convert_days,
                    running_balance=Decimal('0'),
                    notes=f"Year-end conversion to {target_type.code}",
                    actor_channel='SYSTEM',
                )
                if actual_convert > 0:
                    LeaveBalanceLedger.objects.create(
                        employee=employee, leave_type=target_type, year=ending_year,
                        txn_type='CREDIT_CONVERSION', days=actual_convert,
                        running_balance=target_balance.available,
                        notes=f"Year-end conversion from {lt.code}",
                        actor_channel='SYSTEM',
                    )

                if lapse_remainder > 0:
                    balance.lapsed = lapse_remainder
                    balance.save()

            summary.append({
                'employee': employee.employee_id, 'type': lt.code,
                'action': 'CONVERT', 'days': str(convert_days),
            })

        # Step 2: CARRY types (EL)
        for lt in LeaveType.objects.filter(year_end_action='CARRY', is_active=True):
            balance = LeaveBalance.objects.filter(
                employee=employee, leave_type=lt, year=ending_year
            ).first()
            if not balance:
                continue

            available = balance.available
            carry_max = Decimal(str(lt.carry_forward_max))
            carry_days = min(available, carry_max) if carry_max > 0 else Decimal('0')
            lapse_days = max(available - carry_days, Decimal('0'))

            if not dry_run:
                balance.lapsed = lapse_days
                balance.save()

                if carry_days > 0:
                    new_balance, _ = LeaveBalance.objects.get_or_create(
                        employee=employee, leave_type=lt, year=new_year,
                        defaults={'entitled': Decimal('0')}
                    )
                    new_balance.carried_forward += carry_days
                    new_balance.save()

                    LeaveBalanceLedger.objects.create(
                        employee=employee, leave_type=lt, year=new_year,
                        txn_type='CREDIT_CARRY_FWD', days=carry_days,
                        running_balance=new_balance.available,
                        notes=f"Carry forward from {ending_year}",
                        actor_channel='SYSTEM',
                    )

                if lapse_days > 0:
                    LeaveBalanceLedger.objects.create(
                        employee=employee, leave_type=lt, year=ending_year,
                        txn_type='LAPSE', days=-lapse_days,
                        running_balance=Decimal('0'),
                        notes=f"Year-end lapse for {ending_year}",
                        actor_channel='SYSTEM',
                    )

            summary.append({
                'employee': employee.employee_id, 'type': lt.code,
                'action': 'CARRY', 'carry': str(carry_days), 'lapse': str(lapse_days),
            })

        # Step 3: LAPSE types (SL, WFH)
        for lt in LeaveType.objects.filter(year_end_action='LAPSE', is_active=True):
            balance = LeaveBalance.objects.filter(
                employee=employee, leave_type=lt, year=ending_year
            ).first()
            if not balance or balance.available <= 0:
                continue

            lapse_days = balance.available

            if not dry_run:
                balance.lapsed = lapse_days
                balance.save()

                LeaveBalanceLedger.objects.create(
                    employee=employee, leave_type=lt, year=ending_year,
                    txn_type='LAPSE', days=-lapse_days,
                    running_balance=Decimal('0'),
                    notes=f"Year-end lapse for {ending_year}",
                    actor_channel='SYSTEM',
                )

            summary.append({
                'employee': employee.employee_id, 'type': lt.code,
                'action': 'LAPSE', 'days': str(lapse_days),
            })

    return summary
