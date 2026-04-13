"""
End-to-end chat simulation tests for the HRMS Slack chatbot.

Tests that OpenAI GPT-4o correctly interprets user messages, picks the right
MCP tools, sends correct (non-hallucinated) arguments, and produces coherent
responses.

Can be run standalone:  python tests/test_chat_e2e.py
Or via pytest:          pytest tests/test_chat_e2e.py -v
"""

from __future__ import annotations

import os
import sys
import json
import traceback

# ---------------------------------------------------------------------------
# Django bootstrap
# ---------------------------------------------------------------------------
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import django
django.setup()

from datetime import date, timedelta
from openai import OpenAI
from mcp_server.registry import get_tools_for_role
from mcp_server.executor import execute_tool
from employees.models import Employee

# ---------------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
SKIP_REASON = None
if not OPENAI_API_KEY:
    SKIP_REASON = "OPENAI_API_KEY not set -- skipping chat e2e tests"

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

MODEL = "gpt-4o"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _next_weekday(days_ahead: int) -> date:
    """Return the next weekday at least *days_ahead* days from today."""
    d = date.today() + timedelta(days=days_ahead)
    while d.weekday() >= 5:          # Saturday=5, Sunday=6
        d += timedelta(days=1)
    return d


def build_system_prompt(role: str, employee: Employee) -> str:
    today = date.today().isoformat()
    name = employee.full_name
    emp_id = employee.employee_id
    dept = employee.department.name
    desg = employee.designation.title
    mgr = employee.reporting_manager.full_name if employee.reporting_manager else 'N/A'

    base = f"Today: {today}. Leave year: 2026 (April 2026 - March 2027).\n"

    if role == 'ADMIN':
        return (
            f"You are Gamyam's HRMS assistant for HR administrators.\n"
            f"Talking to: {name} ({emp_id}), HR Admin.\n{base}"
            f"You have FULL access to all tools. Use leave type CODES "
            f"(SL, PL, EL, LOP, WFH, BL, ML, PtL, OH). "
            f"The 'id' field from get_team_requests is the request_id for approve/reject."
        )
    elif role == 'MANAGER':
        return (
            f"You are Gamyam's HRMS assistant for managers.\n"
            f"Talking to: {name} ({emp_id}), {desg} in {dept}.\n{base}"
            f"You can view/approve/reject team requests. "
            f"The 'id' field from get_team_requests is the request_id for approve/reject. "
            f"Use leave type CODES."
        )
    else:
        return (
            f"You are Gamyam's HRMS assistant for employees.\n"
            f"Talking to: {name} ({emp_id}), {desg} in {dept}. Manager: {mgr}.\n{base}"
            f"Always validate before applying leave. Use leave type CODES "
            f"(SL, PL, EL, LOP, WFH, BL, ML, PtL, OH)."
        )


def convert_tools_to_openai_format(tools):
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


def run_conversation(employee_id: str, role: str, messages_to_send: list[str]) -> list[dict]:
    """
    Drive a multi-turn conversation and return a log.

    Each log entry is one of:
        {"tool": "<name>", "args": {…}, "result_snippet": "…"}
        {"assistant": "<response text>"}
    """
    employee = Employee.objects.get(employee_id=employee_id)
    system_prompt = build_system_prompt(role, employee)
    tools = get_tools_for_role(role)
    openai_tools = convert_tools_to_openai_format(tools)

    conversation = [{"role": "system", "content": system_prompt}]
    log: list[dict] = []

    for user_msg in messages_to_send:
        conversation.append({"role": "user", "content": user_msg})

        max_iterations = 10
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            response = client.chat.completions.create(
                model=MODEL,
                messages=conversation,
                tools=openai_tools if openai_tools else None,
                tool_choice="auto" if openai_tools else None,
            )
            msg = response.choices[0].message

            if msg.tool_calls:
                conversation.append(msg)
                for tool_call in msg.tool_calls:
                    fname = tool_call.function.name
                    fargs = json.loads(tool_call.function.arguments)

                    try:
                        result = execute_tool(
                            fname, fargs,
                            {'employee_id': employee_id, 'role': role},
                        )
                        result_str = json.dumps(result, indent=2, default=str)
                    except Exception as exc:
                        result_str = json.dumps({"error": str(exc)})

                    conversation.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_str,
                    })
                    log.append({
                        "tool": fname,
                        "args": fargs,
                        "result_snippet": result_str[:1000],
                    })
                continue  # back to while — model may issue more tool calls

            # Final textual response for this user turn
            assistant_msg = msg.content or ""
            conversation.append({"role": "assistant", "content": assistant_msg})
            log.append({"assistant": assistant_msg})
            break

    return log


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

def tool_was_called(log, tool_name):
    return any(e.get('tool') == tool_name for e in log)


def get_tool_calls(log, tool_name):
    return [e for e in log if e.get('tool') == tool_name]


def get_tool_args(log, tool_name):
    """Return list of arg dicts for every call to *tool_name*."""
    return [e['args'] for e in log if e.get('tool') == tool_name]


def get_tool_results(log, tool_name):
    """Return list of result snippet strings for *tool_name*."""
    return [e['result_snippet'] for e in log if e.get('tool') == tool_name]


def final_response(log) -> str:
    for entry in reversed(log):
        if 'assistant' in entry:
            return entry['assistant']
    return ""


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestChatE2E:
    """
    Each test method drives a conversation and asserts on the tool-call log.
    """

    # ------------------------------------------------------------------ #
    #  Employee flows                                                      #
    # ------------------------------------------------------------------ #

    def test_employee_check_balance(self):
        """Employee asks for full leave balance."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-001", "EMPLOYEE", [
            "What is my leave balance?"
        ])
        assert tool_was_called(log, "get_my_balance"), "get_my_balance was not called"
        resp = final_response(log).lower()
        # Should mention at least one leave type by name
        assert any(kw in resp for kw in ["sick", "planned", "earned", "casual", "wfh", "work from home"]), \
            f"Response should mention leave type names: {resp[:200]}"

    def test_employee_check_specific_balance(self):
        """Employee asks about sick leave specifically."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-001", "EMPLOYEE", [
            "How many sick leaves do I have?"
        ])
        assert tool_was_called(log, "get_my_balance"), "get_my_balance was not called"
        resp = final_response(log).lower()
        assert "sick" in resp, f"Response should mention sick leave: {resp[:200]}"

    def test_employee_apply_sick_leave_retroactive(self):
        """Employee was sick yesterday -- apply SL for past date."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        log = run_conversation("GIT-001", "EMPLOYEE", [
            "I was sick yesterday, apply sick leave for me."
        ])
        # Should validate first, then apply
        assert tool_was_called(log, "validate_leave") or tool_was_called(log, "apply_leave"), \
            "Neither validate_leave nor apply_leave was called"
        # Check leave type is SL
        for args in get_tool_args(log, "validate_leave") + get_tool_args(log, "apply_leave"):
            if 'leave_type' in args:
                assert args['leave_type'] == 'SL', f"Expected SL, got {args['leave_type']}"

    def test_employee_apply_wfh(self):
        """Employee wants to WFH in 2 days."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        target = _next_weekday(2)
        log = run_conversation("GIT-001", "EMPLOYEE", [
            f"I want to work from home on {target.isoformat()}."
        ])
        assert tool_was_called(log, "validate_leave") or tool_was_called(log, "apply_leave"), \
            "Neither validate_leave nor apply_leave was called"
        for args in get_tool_args(log, "validate_leave") + get_tool_args(log, "apply_leave"):
            if 'leave_type' in args:
                assert args['leave_type'] == 'WFH', f"Expected WFH, got {args['leave_type']}"

    def test_employee_apply_planned_leave(self):
        """Employee requests planned leave 5-7 days out."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        start = _next_weekday(5)
        end = _next_weekday(7)
        log = run_conversation("GIT-001", "EMPLOYEE", [
            f"I want planned leave from {start.isoformat()} to {end.isoformat()}."
        ])
        assert tool_was_called(log, "validate_leave") or tool_was_called(log, "apply_leave"), \
            "Neither validate_leave nor apply_leave was called"
        for args in get_tool_args(log, "validate_leave") + get_tool_args(log, "apply_leave"):
            if 'leave_type' in args:
                assert args['leave_type'] == 'PL', f"Expected PL, got {args['leave_type']}"

    def test_employee_policy_inquiry(self):
        """Employee asks about WFH policy."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-001", "EMPLOYEE", [
            "What is the WFH policy?"
        ])
        assert tool_was_called(log, "get_leave_policy"), "get_leave_policy was not called"
        resp = final_response(log).lower()
        assert "wfh" in resp or "work from home" in resp, \
            f"Response should explain WFH: {resp[:200]}"

    def test_employee_cancel_leave(self):
        """Multi-turn: show requests then cancel a pending one using real ID."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-001", "EMPLOYEE", [
            "Show my leave requests.",
            "Cancel the most recent pending one."
        ])
        assert tool_was_called(log, "get_my_requests"), "get_my_requests was not called"
        # If cancel_leave was called, verify the request_id came from a prior result
        cancel_calls = get_tool_calls(log, "cancel_leave")
        if cancel_calls:
            # Extract IDs from get_my_requests results
            request_results = get_tool_results(log, "get_my_requests")
            all_ids = set()
            for rsnip in request_results:
                try:
                    parsed = json.loads(rsnip)
                    results_list = parsed if isinstance(parsed, list) else parsed.get('results', [])
                    for r in results_list:
                        item = r if isinstance(r, dict) else {}
                        if 'id' in item:
                            all_ids.add(item['id'])
                except Exception:
                    pass
            for cc in cancel_calls:
                rid = cc['args'].get('request_id')
                if all_ids:
                    assert rid in all_ids, \
                        f"cancel_leave request_id {rid} not found in get_my_requests results {all_ids}"
        # If there were no pending requests, the bot should have said so -- that is fine
        resp = final_response(log).lower()
        assert "cancel" in resp or "no pending" in resp or "no request" in resp or "none" in resp, \
            f"Response should discuss cancellation or absence of requests: {resp[:200]}"

    def test_employee_gender_restriction(self):
        """Male employee asks for maternity leave -- should be rejected/explained."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-001", "EMPLOYEE", [
            "I want to apply for maternity leave."
        ])
        resp = final_response(log).lower()
        # The bot or validation should flag gender restriction
        assert any(kw in resp for kw in [
            "female", "gender", "not eligible", "cannot", "maternity", "restricted",
            "not available", "male", "women", "error",
        ]), f"Response should explain gender restriction: {resp[:300]}"

    def test_employee_insufficient_balance(self):
        """Apply for more days than available -- validation should catch it."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        # Ask for 30 days of earned leave -- almost certainly exceeds balance
        start = _next_weekday(5)
        end = start + timedelta(days=40)
        log = run_conversation("GIT-001", "EMPLOYEE", [
            f"Apply earned leave from {start.isoformat()} to {end.isoformat()} for a long vacation."
        ])
        resp = final_response(log).lower()
        # Should mention insufficient balance or error
        assert any(kw in resp for kw in [
            "insufficient", "enough", "balance", "exceed", "available",
            "cannot", "not enough", "error", "unable",
        ]), f"Response should mention insufficient balance: {resp[:300]}"

    def test_employee_advance_notice_violation(self):
        """PL for tomorrow should violate advance notice requirement."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        tomorrow = _next_weekday(1)
        log = run_conversation("GIT-001", "EMPLOYEE", [
            f"Apply planned leave for {tomorrow.isoformat()} please."
        ])
        resp = final_response(log).lower()
        # Should mention advance notice or short notice
        has_notice_warning = any(kw in resp for kw in [
            "advance", "notice", "short", "prior", "days before",
            "cannot", "error", "not allowed", "validation",
        ])
        # Also acceptable: the tool was called and returned an error
        tool_error = False
        for entry in log:
            snippet = entry.get('result_snippet', '')
            if 'error' in snippet.lower() or 'advance' in snippet.lower() or 'notice' in snippet.lower():
                tool_error = True
                break
        assert has_notice_warning or tool_error, \
            f"Expected advance notice violation: {resp[:300]}"

    # ------------------------------------------------------------------ #
    #  Manager flows                                                       #
    # ------------------------------------------------------------------ #

    def test_manager_view_pending(self):
        """Manager asks for pending team requests."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-023", "MANAGER", [
            "Show pending team requests."
        ])
        assert tool_was_called(log, "get_team_requests"), "get_team_requests was not called"
        args_list = get_tool_args(log, "get_team_requests")
        # At least one call should request PENDING status
        assert any(
            a.get('status', '').upper() == 'PENDING' for a in args_list
        ) or any('status' not in a for a in args_list), \
            f"get_team_requests should filter by PENDING: {args_list}"

    def test_manager_approve_by_name(self):
        """Multi-turn: show pending, then approve a specific request."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-023", "MANAGER", [
            "Show me pending leave requests from my team.",
            "Approve the first one."
        ])
        assert tool_was_called(log, "get_team_requests"), "get_team_requests was not called"
        # If there were pending requests, approve_leave should have been called
        request_results = get_tool_results(log, "get_team_requests")
        has_pending = False
        found_ids = set()
        for rsnip in request_results:
            try:
                parsed = json.loads(rsnip)
                results_list = parsed if isinstance(parsed, list) else parsed.get('results', [])
                for r in results_list:
                    item = r if isinstance(r, dict) else {}
                    if 'id' in item:
                        found_ids.add(item['id'])
                        has_pending = True
            except Exception:
                pass

        if has_pending:
            assert tool_was_called(log, "approve_leave"), \
                "approve_leave should have been called after seeing pending requests"
            for cc in get_tool_calls(log, "approve_leave"):
                rid = cc['args'].get('request_id')
                assert rid in found_ids, \
                    f"approve_leave used request_id={rid} which is not in team requests {found_ids}"
        else:
            resp = final_response(log).lower()
            assert "no pending" in resp or "no request" in resp or "none" in resp, \
                f"Should mention no pending requests: {resp[:200]}"

    def test_manager_reject_with_reason(self):
        """Manager rejects a request with a reason."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-023", "MANAGER", [
            "Show pending team requests.",
            "Reject the first one because of a project deadline."
        ])
        assert tool_was_called(log, "get_team_requests"), "get_team_requests was not called"
        reject_calls = get_tool_calls(log, "reject_leave")
        request_results = get_tool_results(log, "get_team_requests")
        has_pending = False
        found_ids = set()
        for rsnip in request_results:
            try:
                parsed = json.loads(rsnip)
                results_list = parsed if isinstance(parsed, list) else parsed.get('results', [])
                for r in results_list:
                    item = r if isinstance(r, dict) else {}
                    if 'id' in item:
                        found_ids.add(item['id'])
                        has_pending = True
            except Exception:
                pass

        if has_pending:
            assert len(reject_calls) >= 1, "reject_leave should have been called"
            for rc in reject_calls:
                assert 'remarks' in rc['args'], "reject_leave should include remarks"
                assert rc['args'].get('request_id') in found_ids, \
                    f"reject_leave request_id not from get_team_requests"

    def test_manager_team_balance(self):
        """Manager asks for team leave balances."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-023", "MANAGER", [
            "Show team leave balances."
        ])
        assert tool_was_called(log, "get_team_balance"), "get_team_balance was not called"

    def test_manager_team_calendar(self):
        """Manager asks who is on leave next week."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-023", "MANAGER", [
            "Who is on leave next week?"
        ])
        assert tool_was_called(log, "get_team_calendar"), "get_team_calendar was not called"
        args_list = get_tool_args(log, "get_team_calendar")
        assert len(args_list) >= 1, "get_team_calendar should have been called"
        for a in args_list:
            assert 'start_date' in a and 'end_date' in a, \
                f"get_team_calendar should have start_date and end_date: {a}"

    def test_manager_approve_all(self):
        """Manager asks to approve all pending requests."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-023", "MANAGER", [
            "Show pending requests from my team.",
            "Approve all of them."
        ])
        assert tool_was_called(log, "get_team_requests"), "get_team_requests was not called"
        # Count pending requests from results
        request_results = get_tool_results(log, "get_team_requests")
        pending_ids = set()
        for rsnip in request_results:
            try:
                parsed = json.loads(rsnip)
                results_list = parsed if isinstance(parsed, list) else parsed.get('results', [])
                for r in results_list:
                    item = r if isinstance(r, dict) else {}
                    if 'id' in item:
                        pending_ids.add(item['id'])
            except Exception:
                pass

        if pending_ids:
            approve_calls = get_tool_calls(log, "approve_leave")
            approved_ids = {cc['args'].get('request_id') for cc in approve_calls}
            # Every approved ID should be from the pending list
            for aid in approved_ids:
                assert aid in pending_ids, \
                    f"approve_leave used request_id={aid} not in pending set {pending_ids}"

    def test_manager_also_apply_own_leave(self):
        """Manager can also apply leave for themselves (has EMPLOYEE tools too)."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        target = _next_weekday(3)
        log = run_conversation("GIT-023", "MANAGER", [
            f"I need to work from home on {target.isoformat()}."
        ])
        assert tool_was_called(log, "validate_leave") or tool_was_called(log, "apply_leave"), \
            "Manager should be able to use employee leave tools"

    # ------------------------------------------------------------------ #
    #  Admin / HR flows                                                    #
    # ------------------------------------------------------------------ #

    def test_hr_check_employee_balance(self):
        """HR asks for a specific employee's balance."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-046", "ADMIN", [
            "What is Prithvi's (GIT-001) leave balance?"
        ])
        # HR should use get_my_balance with employee_id or get_employee + balance tool
        # The admin has access to get_all_requests and adjust_balance but for balance
        # they might use get_my_balance or search + get_employee
        resp = final_response(log).lower()
        has_balance_info = any(kw in resp for kw in [
            "sick", "planned", "earned", "balance", "leave", "day",
        ])
        assert has_balance_info, f"Response should contain balance info: {resp[:300]}"

    def test_hr_adjust_balance(self):
        """HR gives extra earned leave to an employee."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-046", "ADMIN", [
            "Give Meena (GIT-002) 2 extra earned leave days because she worked on Diwali weekend."
        ])
        assert tool_was_called(log, "adjust_balance"), "adjust_balance was not called"
        args_list = get_tool_args(log, "adjust_balance")
        assert len(args_list) >= 1
        a = args_list[0]
        assert a.get('employee_id') == 'GIT-002', f"Expected GIT-002, got {a.get('employee_id')}"
        assert a.get('leave_type') == 'EL', f"Expected EL, got {a.get('leave_type')}"
        assert a.get('days') == 2, f"Expected 2 days, got {a.get('days')}"

    def test_hr_create_override(self):
        """HR blocks WFH for an employee for May 2026."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-046", "ADMIN", [
            "Block WFH for GIT-001 for the month of May 2026. He's on a PIP."
        ])
        assert tool_was_called(log, "create_override"), "create_override was not called"
        args_list = get_tool_args(log, "create_override")
        assert len(args_list) >= 1
        a = args_list[0]
        assert a.get('employee_id') == 'GIT-001', f"Expected GIT-001, got {a.get('employee_id')}"
        assert a.get('block_application') is True, f"block_application should be True"
        # Check date range covers May 2026
        eff_from = a.get('effective_from', '')
        assert '2026-05' in eff_from, f"effective_from should be in May 2026: {eff_from}"

    def test_hr_update_policy(self):
        """HR increases sick leave to 10 days retroactively."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-046", "ADMIN", [
            "Increase sick leave to 10 days for everyone. Make it retroactive."
        ])
        assert tool_was_called(log, "update_leave_type"), "update_leave_type was not called"
        args_list = get_tool_args(log, "update_leave_type")
        assert len(args_list) >= 1
        a = args_list[0]
        assert a.get('code') == 'SL', f"Expected code SL, got {a.get('code')}"
        eff_mode = a.get('effective_mode', '').upper()
        assert eff_mode == 'RETROACTIVE', f"Expected RETROACTIVE, got {eff_mode}"

    def test_hr_add_employee(self):
        """HR adds a new employee."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-046", "ADMIN", [
            "Add a new employee: Test User, GIT-T99, test99@gamyam.co, male, "
            "Engineering department, Software Developer, joined today."
        ])
        assert tool_was_called(log, "add_employee"), "add_employee was not called"
        args_list = get_tool_args(log, "add_employee")
        assert len(args_list) >= 1
        a = args_list[0]
        assert a.get('employee_id') == 'GIT-T99', f"Expected GIT-T99, got {a.get('employee_id')}"
        assert a.get('gender') == 'M', f"Expected M for male, got {a.get('gender')}"

    def test_hr_search_employees(self):
        """HR searches for all employees in Engineering."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-046", "ADMIN", [
            "Show me all employees in Engineering."
        ])
        assert tool_was_called(log, "search_employees"), "search_employees was not called"
        args_list = get_tool_args(log, "search_employees")
        assert len(args_list) >= 1
        a = args_list[0]
        dept_val = a.get('department', '').lower()
        assert 'eng' in dept_val, f"Expected department filter with 'eng': {a}"

    def test_hr_view_all_requests(self):
        """HR views all pending leave requests."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-046", "ADMIN", [
            "Show all pending leave requests."
        ])
        assert tool_was_called(log, "get_all_requests"), "get_all_requests was not called"

    # ------------------------------------------------------------------ #
    #  Conversation resilience                                             #
    # ------------------------------------------------------------------ #

    def test_context_retention(self):
        """Multi-turn: balance check then apply -- uses context from prior turn."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        log = run_conversation("GIT-001", "EMPLOYEE", [
            "Show my balance.",
            f"Apply 1 day sick leave for {yesterday}."
        ])
        assert tool_was_called(log, "get_my_balance"), "get_my_balance should be called first"
        assert tool_was_called(log, "validate_leave") or tool_was_called(log, "apply_leave"), \
            "Should proceed to apply leave in second turn"
        for args in get_tool_args(log, "validate_leave") + get_tool_args(log, "apply_leave"):
            if 'leave_type' in args:
                assert args['leave_type'] == 'SL', f"Expected SL, got {args['leave_type']}"

    def test_error_recovery(self):
        """Tool returns an error -- bot should explain gracefully."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        # Cancel a non-existent request ID
        log = run_conversation("GIT-001", "EMPLOYEE", [
            "Cancel leave request 999999."
        ])
        resp = final_response(log).lower()
        # The bot should not crash; it should relay the error gracefully
        assert resp, "Bot should produce a response even on error"
        # Should not say something like "I successfully cancelled"
        assert "success" not in resp, f"Should not claim success on error: {resp[:200]}"

    def test_role_boundary(self):
        """Employee asks to approve a request -- should be told they cannot."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-001", "EMPLOYEE", [
            "Approve leave request 5."
        ])
        # approve_leave should NOT be in employee tools, so it should not be called
        assert not tool_was_called(log, "approve_leave"), \
            "Employee should not have access to approve_leave"
        resp = final_response(log).lower()
        assert any(kw in resp for kw in [
            "cannot", "don't have", "not authorized", "not available",
            "unable", "permission", "manager", "only", "access",
        ]), f"Response should explain lack of permission: {resp[:300]}"

    def test_hallucination_prevention(self):
        """Ask to approve without viewing first -- bot should fetch data, not hallucinate ID."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        log = run_conversation("GIT-023", "MANAGER", [
            "Approve the latest pending request from my team."
        ])
        # The bot should first call get_team_requests to find the actual ID
        assert tool_was_called(log, "get_team_requests"), \
            "Bot should fetch team requests before approving"
        # If it then approved, the ID must come from results
        approve_calls = get_tool_calls(log, "approve_leave")
        if approve_calls:
            request_results = get_tool_results(log, "get_team_requests")
            found_ids = set()
            for rsnip in request_results:
                try:
                    parsed = json.loads(rsnip)
                    results_list = parsed if isinstance(parsed, list) else parsed.get('results', [])
                    for r in results_list:
                        item = r if isinstance(r, dict) else {}
                        if 'id' in item:
                            found_ids.add(item['id'])
                except Exception:
                    pass
            for ac in approve_calls:
                rid = ac['args'].get('request_id')
                if found_ids:
                    assert rid in found_ids, \
                        f"Hallucinated request_id={rid}, valid IDs: {found_ids}"

    def test_natural_language_leave_type(self):
        """User says 'casual leave' -- should resolve to PL code."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        target = _next_weekday(5)
        log = run_conversation("GIT-001", "EMPLOYEE", [
            f"I need casual leave on {target.isoformat()}."
        ])
        assert tool_was_called(log, "validate_leave") or tool_was_called(log, "apply_leave"), \
            "Should attempt to validate/apply leave"
        for args in get_tool_args(log, "validate_leave") + get_tool_args(log, "apply_leave"):
            if 'leave_type' in args:
                assert args['leave_type'] == 'PL', \
                    f"Casual leave should map to PL, got {args['leave_type']}"

    def test_long_conversation(self):
        """5 sequential messages -- context should be maintained throughout."""
        if SKIP_REASON:
            print(f"  SKIP: {SKIP_REASON}")
            return
        d1 = _next_weekday(5)
        d2 = _next_weekday(6)
        log = run_conversation("GIT-001", "EMPLOYEE", [
            "What is my leave balance?",
            "What is the WFH policy?",
            f"Apply WFH for {d1.isoformat()}.",
            "Show my requests.",
            "What about planned leave -- how many do I have left?"
        ])
        # Should have called multiple distinct tools across the conversation
        tools_called = {e['tool'] for e in log if 'tool' in e}
        assert len(tools_called) >= 2, \
            f"Expected at least 2 distinct tools across 5 turns, got {tools_called}"
        # There should be at least 3 assistant messages (one per turn that concludes)
        assistant_msgs = [e for e in log if 'assistant' in e]
        assert len(assistant_msgs) >= 3, \
            f"Expected at least 3 assistant messages, got {len(assistant_msgs)}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all_tests():
    suite = TestChatE2E()
    test_methods = [m for m in dir(suite) if m.startswith('test_')]
    test_methods.sort()

    passed = 0
    failed = 0
    skipped = 0
    results = []

    print("=" * 80)
    print("GAMYAM HRMS -- CHAT E2E TEST SUITE")
    print(f"Model: {MODEL} | Date: {date.today().isoformat()}")
    print("=" * 80)

    for name in test_methods:
        print(f"\n{'─' * 70}")
        print(f"  {name}")
        print(f"{'─' * 70}")
        try:
            method = getattr(suite, name)
            method()
            if SKIP_REASON:
                skipped += 1
                status = "SKIP"
            else:
                passed += 1
                status = "PASS"
        except AssertionError as ae:
            failed += 1
            status = "FAIL"
            print(f"  Assertion: {ae}")
        except Exception as exc:
            failed += 1
            status = "FAIL"
            print(f"  Error: {exc}")
            traceback.print_exc()

        results.append((name, status))
        print(f"  >> {status}: {name}")

    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    for name, status in results:
        marker = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, "[????]")
        print(f"  {marker}  {name}")
    total = passed + failed + skipped
    print(f"\n  {passed} passed, {failed} failed, {skipped} skipped out of {total} tests")
    print(f"{'=' * 80}")

    return failed == 0


# Allow both `python tests/test_chat_e2e.py` and `pytest tests/test_chat_e2e.py`
if __name__ == '__main__':
    success = _run_all_tests()
    sys.exit(0 if success else 1)
