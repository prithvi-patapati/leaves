import logging

logger = logging.getLogger('notifications')


def notify_leave_applied(leave_request):
    approver_name = leave_request.current_approver.full_name if leave_request.current_approver else 'N/A'
    logger.info(
        f"[LEAVE_APPLIED] {leave_request.employee.full_name} applied for "
        f"{leave_request.leave_type.name} ({leave_request.start_date} to {leave_request.end_date}). "
        f"Sent to: {approver_name}"
    )


def notify_leave_approved(leave_request):
    logger.info(
        f"[LEAVE_APPROVED] {leave_request.employee.full_name}'s {leave_request.leave_type.name} "
        f"approved by {leave_request.approved_by.full_name}"
    )


def notify_leave_rejected(leave_request):
    logger.info(
        f"[LEAVE_REJECTED] {leave_request.employee.full_name}'s {leave_request.leave_type.name} "
        f"rejected by {leave_request.rejected_by.full_name}: {leave_request.rejection_remarks}"
    )


def notify_leave_cancelled(leave_request):
    logger.info(
        f"[LEAVE_CANCELLED] {leave_request.employee.full_name} cancelled "
        f"{leave_request.leave_type.name} ({leave_request.start_date} to {leave_request.end_date})"
    )


def notify_policy_change(policy_version):
    changed_by = policy_version.changed_by.full_name if policy_version.changed_by else 'System'
    logger.info(
        f"[POLICY_CHANGED] {policy_version.leave_type.name}: {policy_version.change_summary}. "
        f"Changed by: {changed_by}. "
        f"Email would be sent to all active employees."
    )


def notify_balance_adjustment(employee, leave_type, days, reason):
    logger.info(
        f"[BALANCE_ADJUSTED] {employee.full_name}: {days:+} {leave_type.name}. Reason: {reason}"
    )


def notify_hr_flag(leave_request, flag_type):
    logger.info(
        f"[HR_FLAG] {leave_request.employee.full_name}: {flag_type} — "
        f"{leave_request.leave_type.name} for {leave_request.duration_days} continuous days"
    )
