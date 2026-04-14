"""
Gamyam HRMS — Slack Connector

Role switching via slash commands:
  /employee GIT-001    → become Prithvi (employee view)
  /hr                  → become Bhavishya (HR admin view)
  /manager GIT-023     → become Chandrakala (manager view)
  /whoami              → show current role
  /reset               → clear conversation history
"""

import os
import json
import logging
import re
import requests
from datetime import date
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from openai import OpenAI

HRMS_API_URL = os.environ.get('HRMS_API_URL', 'http://localhost:8000')
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_APP_TOKEN = os.environ.get('SLACK_APP_TOKEN')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('slack_connector')

sessions = {}

# ── Production System Prompts ──

EMPLOYEE_PROMPT = """You are Gamyam's leave assistant for {name} ({emp_id}).
Department: {dept} | Role: {designation} | Manager: {manager}
Today: {today} | Leave year: {leave_year} (Apr {leave_year} – Mar {next_year})

RULES — NEVER BREAK THESE:
1. ONLY discuss leave management. Anything else: "I only handle leave management."
2. NEVER fabricate data. If a tool returns empty or errors, say so plainly.
3. NEVER skip validation. Call validate_leave before apply_leave. No exceptions.
4. NEVER auto-submit. Confirm with the user before calling apply_leave.
5. Use leave type CODES: SL=Sick, PL=Planned/Casual, EL=Earned, LOP=Loss of Pay, WFH=Work From Home, BL=Bereavement, ML=Maternity, PtL=Paternity, OH=Optional Holiday.
6. All dates in YYYY-MM-DD format when calling tools.
7. If is_half_day, always ask AM or PM.
8. Generate idempotency_key as: {emp_id}_action_{today}_XXXX (random 4 chars).

HANDLING REQUESTS:
- "What's my balance?" → call get_my_balance, present each type with available days.
- "Apply leave" → identify type from context (sick/unwell→SL, planned/vacation→PL, WFH→WFH), confirm dates, call get_my_balance to check, call validate_leave, confirm with user, then apply_leave.
- "Cancel leave" → call get_my_requests to find it, confirm, then cancel_leave.
- "Policy question" → call get_leave_policy, explain in plain English.
- If insufficient balance, suggest alternatives (split across types, or use LOP).
- If validation fails, explain why and suggest fixes.

INTERACTIVE BUTTONS appear automatically after validate_leave succeeds. Do NOT describe buttons in text — just present clear data.

Be concise, friendly. Use their first name."""

MANAGER_PROMPT = """You are Gamyam's leave assistant for {name} ({emp_id}), a manager.
Department: {dept} | Role: {designation}
Today: {today} | Leave year: {leave_year}

RULES — NEVER BREAK THESE:
1. ONLY discuss leave management.
2. NEVER fabricate data. Only state facts from tool results.
3. NEVER approve without showing details first. Display the request, then ask for confirmation.
4. NEVER reject without a reason. Insist: "I need a reason — the employee will see it."
5. Use the 'id' field from get_team_requests as request_id for approve/reject. NEVER guess IDs.
6. NEVER modify policies or create overrides. Say: "That's an HR function."
7. Generate idempotency_key as: MGR_{emp_id}_action_{today}_XXXX.

HANDLING REQUESTS:
- "What's pending?" → call get_team_requests(status=PENDING), list each with employee name, type, dates, reason.
- "Approve" → show details first, confirm, then call approve_leave.
- "Approve all" → list all pending, confirm, then approve each.
- "Reject" → ask for reason, then call reject_leave with remarks.
- "Team calendar" → call get_team_calendar with date range.
- "Team balance" → call get_team_balance, highlight anyone running low.
- Own leave → same flow as employee.

INTERACTIVE BUTTONS: Approve/Reject buttons appear automatically on pending request cards. Do NOT describe buttons in text.

Be professional, brief. Present info in scannable format."""

ADMIN_PROMPT = """You are Gamyam's HRMS assistant for {name} ({emp_id}), an HR administrator.
Today: {today} | Leave year: {leave_year}

You have FULL access to all 48 tools: leave policy management, employee management, overrides, balance adjustments, org structure, bulk operations, system operations, and HR action queue.

RULES — NEVER BREAK THESE:
1. ONLY discuss HRMS operations.
2. NEVER fabricate data. Only state facts from tool results.
3. NEVER auto-execute destructive actions. ALWAYS confirm before: policy changes, bulk overrides, balance adjustments, year-end processing, employee deactivation.
4. For policy changes, ALWAYS ask: "Prospective (next cycle) or retroactive (adjust current balances)?"
5. Before creating overrides, call get_overrides first to check for conflicts.
6. NEVER run year-end without dry_run=true first.
7. Generate idempotency_key as: HR_{emp_id}_action_{today}_XXXX.

CLASSIFY REQUESTS:
- "Change SL to 10 days" → update_leave_type (affects everyone)
- "Block Prithvi's WFH" → create_override (one person)
- "Give Meena 2 extra EL" → adjust_balance (one-time credit)
- "New employee joined" → add_employee
- "Move Prithvi to Sales" → transfer_employee
- "Who's on leave today?" → get_all_requests
- "Run year-end" → trigger_year_end (dry_run first!)
- If ambiguous, ask: "Do you mean for one person (override) or everyone (policy change)?"

INTERACTIVE BUTTONS appear automatically on approval cards and confirmations. Do NOT describe buttons in text.

When tool results are empty, say so clearly: "No leave types configured yet. Want me to create one?"
Be efficient, professional. Summarize, don't dump raw data. Flag side effects proactively."""

app = App(token=SLACK_BOT_TOKEN)
openai_client = OpenAI(api_key=OPENAI_API_KEY)


# ── HRMS API Client ──

def hrms_get_tools(role):
    try:
        resp = requests.post(f'{HRMS_API_URL}/api/v1/tools/list', json={'role': role}, timeout=10)
        resp.raise_for_status()
        return resp.json().get('tools', [])
    except Exception as e:
        logger.error(f"Failed to fetch tools: {e}")
        return []


def hrms_execute_tool(tool_name, args, employee_id, role):
    try:
        resp = requests.post(
            f'{HRMS_API_URL}/api/v1/tools/execute',
            json={'tool': tool_name, 'args': args, 'employee_id': employee_id, 'role': role},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get('result', {})
    except requests.exceptions.HTTPError as e:
        try:
            return {'error': e.response.json().get('error', str(e))}
        except Exception:
            return {'error': str(e)}
    except Exception as e:
        return {'error': str(e)}


def hrms_get_employee(employee_id):
    try:
        resp = requests.get(f'{HRMS_API_URL}/api/v1/employees/{employee_id}/', timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def hrms_get_all_employees():
    try:
        resp = requests.get(f'{HRMS_API_URL}/api/v1/employees/', timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


# ── Employee Input Resolver ──

def _normalize(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def resolve_employee_input(text):
    raw = text.strip().strip('`').strip()
    if not raw:
        return None, "Please provide an employee ID or name."

    candidate = raw.upper().replace(' ', '')
    emp = hrms_get_employee(candidate)
    if emp:
        return emp['employee_id'], None

    digits = re.sub(r'[^0-9]', '', raw)
    if digits:
        padded = f"GIT-{digits.zfill(3)}"
        emp = hrms_get_employee(padded)
        if emp:
            return emp['employee_id'], None

    all_emps = hrms_get_all_employees()
    if not all_emps:
        return None, f"Could not find `{raw}` and employee list is unavailable."

    query = _normalize(raw)

    for e in all_emps:
        if _normalize(e.get('full_name', '')) == query:
            return e['employee_id'], None
        first = e.get('full_name', '').split()[0] if e.get('full_name') else ''
        if first and _normalize(first) == query:
            return e['employee_id'], None

    substring_matches = []
    for e in all_emps:
        name_norm = _normalize(e.get('full_name', ''))
        if query in name_norm or name_norm in query:
            substring_matches.append(e)
    if len(substring_matches) == 1:
        return substring_matches[0]['employee_id'], None
    if len(substring_matches) > 1:
        options = "\n".join(f"• `{e['employee_id']}` — {e.get('full_name', '')}" for e in substring_matches[:8])
        return None, f"Multiple matches for *{raw}*:\n{options}\n\nPlease use the ID to be specific."

    def similarity(a, b):
        common = sum(1 for c in set(a) if c in b)
        return (2.0 * common) / (len(set(a)) + len(set(b))) if a and b else 0

    scored = []
    for e in all_emps:
        name = e.get('full_name', '')
        best = max(similarity(query, _normalize(name)),
                   similarity(query, _normalize(name.split()[0] if name else '')))
        if best > 0.5:
            scored.append((best, e))

    scored.sort(key=lambda x: -x[0])
    if scored:
        suggestions = "\n".join(f"• `{e['employee_id']}` — {e.get('full_name', '')}" for _, e in scored[:5])
        return None, f"Couldn't find *{raw}*. Did you mean:\n{suggestions}"

    return None, f"No employee found matching `{raw}`. Try an ID like `GIT-001` or a name like `Prithvi`."


# ── System Prompts ──

def build_system_prompt(role, emp):
    name = emp.get('full_name', 'Unknown')
    emp_id = emp.get('employee_id', 'Unknown')
    dept = emp.get('department', {})
    dept_name = dept.get('name', dept) if isinstance(dept, dict) else str(dept)
    desg = emp.get('designation', {})
    desg_name = desg.get('title', desg) if isinstance(desg, dict) else str(desg)
    mgr = emp.get('reporting_manager', {})
    mgr_name = mgr.get('full_name', 'N/A') if isinstance(mgr, dict) else str(mgr) if mgr else 'N/A'
    today = date.today().isoformat()
    leave_year = str(date.today().year) if date.today().month >= 4 else str(date.today().year - 1)
    next_year = str(int(leave_year) + 1)

    fmt = dict(
        name=name, emp_id=emp_id, dept=dept_name, designation=desg_name,
        manager=mgr_name, today=today, leave_year=leave_year, next_year=next_year,
    )

    if role == 'ADMIN':
        prompt = ADMIN_PROMPT.format(**fmt)
        # For admin, add dynamic context about configured leave types
        try:
            resp = requests.get(f'{HRMS_API_URL}/api/v1/leaves/policy/', timeout=5)
            if resp.status_code == 200:
                types = resp.json()
                if types:
                    type_list = ', '.join(f"{t['code']}" for t in types)
                    prompt += f"\n\nActive leave types: {type_list}"
                else:
                    prompt += "\n\nNo leave types configured yet. HR may want to create them."
        except Exception:
            pass
        return prompt
    elif role == 'MANAGER':
        return MANAGER_PROMPT.format(**fmt)
    else:
        return EMPLOYEE_PROMPT.format(**fmt)


def to_openai_tools(tools):
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
             "parameters": t["input_schema"]}} for t in tools]


# ── Session Management ──

def get_session(uid):
    if uid not in sessions:
        sessions[uid] = {'employee_id': None, 'role': None, 'name': None,
                         'conversation': [], 'tools': [], 'openai_tools': [], 'system_prompt': None}
    return sessions[uid]


def set_role(uid, text_input, role):
    session = get_session(uid)

    employee_id, err = resolve_employee_input(text_input)
    if err:
        return err

    emp = hrms_get_employee(employee_id)
    if not emp:
        return f"Could not find employee `{employee_id}`."

    tools = hrms_get_tools(role)
    if not tools:
        return f"Could not fetch tools for role `{role}`. Is the API running?"

    session.update({
        'employee_id': employee_id,
        'role': role,
        'name': emp.get('full_name', employee_id),
        'conversation': [],
        'tools': tools,
        'openai_tools': to_openai_tools(tools),
        'system_prompt': build_system_prompt(role, emp),
    })

    label = {'EMPLOYEE': 'Employee', 'MANAGER': 'Manager', 'ADMIN': 'HR Admin'}[role]
    return f"Switched to *{label}* mode as *{session['name']}* (`{employee_id}`)\n_{len(tools)} tools loaded. Start chatting!_"


# ── Block Kit Helpers ──

def _format_balance_blocks(text_reply, tool_results):
    """Format balance data as clean Slack blocks."""
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text_reply}},
    ]

    for tc in tool_results:
        if tc["tool"] not in ("get_my_balance", "get_team_balance"):
            continue
        result = tc["result"]
        if isinstance(result, dict) and result.get("error"):
            continue

        # Build a monospace table from the balance data
        balances = result if isinstance(result, list) else result.get("results", result.get("balances", [])) if isinstance(result, dict) else []
        if not balances:
            continue

        blocks.append({"type": "divider"})

        for bal in balances:
            # Handle team balance (has employee info) or personal balance
            emp_name = bal.get("employee_name", bal.get("employee_code", ""))
            leave_type = bal.get("leave_type_name", bal.get("leave_type_code", ""))
            total = bal.get("entitled", bal.get("total", "N/A"))
            used = bal.get("used", "N/A")
            available = bal.get("available", "N/A")

            line_parts = []
            if emp_name:
                line_parts.append(f"*{emp_name}*")
            line_parts.append(f"`{leave_type}`  Total: `{total}` | Used: `{used}` | Available: `{available}`")
            text = "  ".join(line_parts) if line_parts else str(bal)

            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})

    return blocks


def _format_team_requests_blocks(text_reply, tool_results, employee_id, role):
    """Format pending requests with approve/reject buttons."""
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text_reply}},
    ]

    for tc in tool_results:
        if tc["tool"] != "get_team_requests":
            continue
        result = tc["result"]
        if isinstance(result, dict) and result.get("error"):
            continue

        requests_list = result if isinstance(result, list) else result.get("results", result.get("requests", [])) if isinstance(result, dict) else []
        if not requests_list:
            continue

        for req in requests_list:
            request_id = req.get("id", req.get("request_id"))
            emp_name = req.get("employee_name", req.get("employee", "Unknown"))
            leave_type = req.get("leave_type", req.get("leave_type_code", "N/A"))
            start_date = req.get("start_date", req.get("from_date", "N/A"))
            end_date = req.get("end_date", req.get("to_date", "N/A"))
            reason = req.get("reason", req.get("remarks", "No reason provided"))
            status = req.get("status", "")

            blocks.append({"type": "divider"})

            detail_text = (
                f"*{emp_name}* — `{leave_type}`\n"
                f"Dates: {start_date} to {end_date}\n"
                f"Reason: _{reason}_\n"
                f"Request ID: `{request_id}`"
            )
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": detail_text}})

            # Only show buttons for pending requests
            if status.lower() in ("pending", "pending_approval", "") or not status:
                btn_data = json.dumps({
                    "request_id": request_id,
                    "employee_id": employee_id,
                    "role": role,
                    "employee_name": emp_name,
                })
                blocks.append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Approve"},
                            "style": "primary",
                            "action_id": "approve_leave_btn",
                            "value": btn_data,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Reject"},
                            "style": "danger",
                            "action_id": "reject_leave_btn",
                            "value": btn_data,
                        },
                    ],
                })

    return blocks


def _format_leave_confirm_blocks(text_reply, tool_results, employee_id, role):
    """Format leave validation result with confirm/cancel buttons."""
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text_reply}},
    ]

    for tc in tool_results:
        if tc["tool"] != "validate_leave":
            continue
        result = tc["result"]
        if isinstance(result, dict) and result.get("error"):
            continue

        valid = False
        if isinstance(result, dict):
            valid = result.get("valid", result.get("is_valid", False))

        if not valid:
            continue

        # Extract the leave details from the validate_leave arguments
        leave_details = tc["args"].copy()
        # Add reason from conversation context — GPT-4o should have collected it
        # If not available, the apply handler will use a default
        if "reason" not in leave_details:
            leave_details["reason"] = "As discussed"
        leave_details_json = json.dumps({
            "leave_details": leave_details,
            "employee_id": employee_id,
            "role": role,
        })

        blocks.append({"type": "divider"})
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Submit Leave"},
                    "style": "primary",
                    "action_id": "confirm_apply_btn",
                    "value": leave_details_json,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Cancel"},
                    "style": "danger",
                    "action_id": "cancel_apply_btn",
                    "value": "cancel",
                },
            ],
        })

    return blocks


def _format_policy_blocks(text_reply, tool_results):
    """Format leave policy as readable sections."""
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text_reply}},
    ]

    for tc in tool_results:
        if tc["tool"] != "get_leave_policy":
            continue
        result = tc["result"]
        if isinstance(result, dict) and result.get("error"):
            continue

        policies = result if isinstance(result, list) else result.get("results", result.get("leave_types", [])) if isinstance(result, dict) else []
        if not policies:
            continue

        blocks.append({"type": "divider"})

        for policy in policies:
            name = policy.get("name", policy.get("leave_type", "Unknown"))
            code = policy.get("code", policy.get("leave_type_code", ""))
            days = policy.get("days_per_year", policy.get("total_days", policy.get("annual_quota", "N/A")))
            carry = policy.get("carry_forward", policy.get("can_carry_forward", False))
            desc = policy.get("description", "")

            policy_text = f"*{name}* (`{code}`)\n"
            policy_text += f"Annual quota: `{days}` days"
            if carry:
                policy_text += " | Carry forward: Yes"
            if desc:
                policy_text += f"\n_{desc}_"

            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": policy_text}})

    return blocks


def _format_apply_success_blocks(text_reply, tool_results):
    """Format successful leave application as a confirmation block."""
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text_reply}},
    ]

    for tc in tool_results:
        if tc["tool"] != "apply_leave":
            continue
        result = tc["result"]
        if isinstance(result, dict) and result.get("error"):
            continue

        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "Leave request submitted successfully."}],
        })

    return blocks


def _format_approval_success_blocks(text_reply, tool_results):
    """Format approve/reject confirmation."""
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text_reply}},
    ]
    return blocks


def _build_response(text_reply, tool_calls_log, employee_id, role):
    """Main router: check tool calls and return appropriate blocks or plain text."""
    if not tool_calls_log:
        return None

    tool_names = [tc["tool"] for tc in tool_calls_log]

    # Check for team requests with pending items
    if "get_team_requests" in tool_names:
        for tc in tool_calls_log:
            if tc["tool"] == "get_team_requests":
                result = tc["result"]
                has_requests = False
                if isinstance(result, list) and result:
                    has_requests = True
                elif isinstance(result, dict):
                    reqs = result.get("results", result.get("requests", []))
                    if reqs:
                        has_requests = True
                if has_requests:
                    return _format_team_requests_blocks(text_reply, tool_calls_log, employee_id, role)

    # Check for validate_leave with valid=true and no apply_leave called yet
    if "validate_leave" in tool_names and "apply_leave" not in tool_names:
        for tc in tool_calls_log:
            if tc["tool"] == "validate_leave":
                result = tc["result"]
                if isinstance(result, dict) and result.get("valid", result.get("is_valid", False)):
                    return _format_leave_confirm_blocks(text_reply, tool_calls_log, employee_id, role)

    # Check for balance queries
    if "get_my_balance" in tool_names or "get_team_balance" in tool_names:
        return _format_balance_blocks(text_reply, tool_calls_log)

    # Check for successful apply_leave
    if "apply_leave" in tool_names:
        for tc in tool_calls_log:
            if tc["tool"] == "apply_leave":
                result = tc["result"]
                if isinstance(result, dict) and not result.get("error"):
                    return _format_apply_success_blocks(text_reply, tool_calls_log)

    # Check for leave policy
    if "get_leave_policy" in tool_names:
        return _format_policy_blocks(text_reply, tool_calls_log)

    # Check for approve/reject actions
    if "approve_leave" in tool_names or "reject_leave" in tool_names:
        for tc in tool_calls_log:
            if tc["tool"] in ("approve_leave", "reject_leave"):
                result = tc["result"]
                if isinstance(result, dict) and not result.get("error"):
                    return _format_approval_success_blocks(text_reply, tool_calls_log)

    return None


# ── Conversation Engine ──

def process_message(uid, text):
    session = get_session(uid)
    if not session['employee_id']:
        return ("Set a role first:\n• `/employee GIT-001` — login as employee\n"
                "• `/hr` — login as HR admin\n• `/manager GIT-023` — login as manager\n\n"
                "IDs: `GIT-001` Prithvi, `GIT-002` Meena, `GIT-023` Chandrakala, `GIT-046` Bhavishya"), None

    session['conversation'].append({"role": "user", "content": text})
    messages = [{"role": "system", "content": session['system_prompt']}] + session['conversation']

    tool_calls_log = []
    total_tokens = 0

    for _ in range(10):
        try:
            resp = openai_client.chat.completions.create(
                model=OPENAI_MODEL, messages=messages,
                tools=session['openai_tools'] or None,
                tool_choice="auto" if session['openai_tools'] else None,
            )
        except Exception as e:
            return f"LLM error: {e}", None

        if hasattr(resp, 'usage') and resp.usage:
            total_tokens += resp.usage.total_tokens

        msg = resp.choices[0].message

        if msg.tool_calls:
            messages.append(msg)
            for tc in msg.tool_calls:
                fname = tc.function.name
                fargs = json.loads(tc.function.arguments)
                logger.info(f"Tool: {fname}({json.dumps(fargs)[:200]})")

                result = hrms_execute_tool(fname, fargs, session['employee_id'], session['role'])
                result_str = json.dumps(result, default=str)
                logger.info(f"Result: {result_str[:300]}")

                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})

                tool_calls_log.append({
                    "tool": fname,
                    "args": fargs,
                    "result": result,
                })
            continue

        reply = msg.content or "(no response)"

        # Build rich response
        blocks = _build_response(reply, tool_calls_log, session['employee_id'], session['role'])

        logger.info(f"Tokens used: {total_tokens}")

        session['conversation'].append({"role": "assistant", "content": reply})
        if len(session['conversation']) > 40:
            # Keep first 2 messages (system context) + last 30
            # But always keep messages that contain tool results
            keep = []
            for msg in session['conversation'][:-30]:
                if isinstance(msg, dict) and msg.get('role') == 'tool':
                    keep.append(msg)
            session['conversation'] = keep + session['conversation'][-30:]
        return reply, blocks

    return "Too many tool rounds. Try rephrasing.", None


# ── Slash Commands ──

@app.command("/employee")
def cmd_employee(ack, command, say):
    ack()
    text = command.get('text', '').strip()
    if not text:
        say("Usage: `/employee <id or name>`\n\nExamples: `/employee 1`, `/employee Prithvi`, `/employee GIT-001`")
        return
    say(set_role(command['user_id'], text, 'EMPLOYEE'))


@app.command("/hr")
def cmd_hr(ack, command, say):
    ack()
    text = command.get('text', '').strip()
    say(set_role(command['user_id'], text or 'GIT-046', 'ADMIN'))


@app.command("/manager")
def cmd_manager(ack, command, say):
    ack()
    text = command.get('text', '').strip()
    if not text:
        say("Usage: `/manager <id or name>`\n\nExamples: `/manager 23`, `/manager Chandrakala`, `/manager GIT-023`")
        return
    say(set_role(command['user_id'], text, 'MANAGER'))


@app.command("/whoami")
def cmd_whoami(ack, command, say):
    ack()
    s = get_session(command['user_id'])
    if not s['employee_id']:
        say("No role set. Use `/employee`, `/hr`, or `/manager`.")
    else:
        label = {'EMPLOYEE': 'Employee', 'MANAGER': 'Manager', 'ADMIN': 'HR Admin'}.get(s['role'])
        say(f"*{s['name']}* (`{s['employee_id']}`) — {label}")


@app.command("/reset")
def cmd_reset(ack, command, say):
    ack()
    get_session(command['user_id'])['conversation'] = []
    say("Conversation cleared. Role still active.")


# ── Message Handlers ──

@app.event("message")
def on_message(event, say):
    if event.get('bot_id') or event.get('subtype'):
        return
    text = event.get('text', '').strip()
    if not text:
        return
    reply, blocks = process_message(event['user'], text)
    if blocks:
        say(text=reply, blocks=blocks)
    else:
        say(reply)


@app.event("app_mention")
def on_mention(event, say):
    text = re.sub(r'<@[A-Z0-9]+>\s*', '', event.get('text', '')).strip()
    if not text:
        say("Use `/employee GIT-001`, `/hr`, or `/manager GIT-023` to set your role, then chat with me.")
        return
    reply, blocks = process_message(event['user'], text)
    if blocks:
        say(text=reply, blocks=blocks)
    else:
        say(reply)


# ── Interaction Handlers ──

@app.action("approve_leave_btn")
def handle_approve_leave(ack, body, client):
    """Handle Approve button click — approve the leave request immediately."""
    ack()
    user_id = body["user"]["id"]
    user_name = body["user"].get("real_name", body["user"].get("username", "Manager"))
    action = body["actions"][0]
    btn_data = json.loads(action["value"])

    request_id = btn_data["request_id"]
    employee_id = btn_data["employee_id"]
    role = btn_data["role"]
    emp_name = btn_data.get("employee_name", "Employee")

    result = hrms_execute_tool(
        "approve_leave",
        {"request_id": request_id},
        employee_id,
        role,
    )

    if isinstance(result, dict) and not result.get("error"):
        # TODO: Map employee_id to Slack user ID for DM notifications
        logger.info(f"NOTIFICATION: {emp_name}'s leave request was approved by {user_name}")

    # Update the original message to replace buttons with confirmation
    channel = body["channel"]["id"]
    message_ts = body["message"]["ts"]
    original_blocks = body["message"].get("blocks", [])

    # Find and replace the actions block that contained the clicked button
    updated_blocks = []
    for block in original_blocks:
        if block.get("type") == "actions":
            # Check if this actions block contains the approve/reject buttons for this request
            elements = block.get("elements", [])
            matching = any(
                el.get("action_id") in ("approve_leave_btn", "reject_leave_btn")
                and _btn_matches_request(el, request_id)
                for el in elements
            )
            if matching:
                if isinstance(result, dict) and not result.get("error"):
                    updated_blocks.append({
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": f"Approved by {user_name}"}],
                    })
                else:
                    error_msg = result.get("error", "Unknown error") if isinstance(result, dict) else str(result)
                    updated_blocks.append({
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": f"Failed to approve: {error_msg}"}],
                    })
                continue
        updated_blocks.append(block)

    try:
        client.chat_update(
            channel=channel,
            ts=message_ts,
            text=body["message"].get("text", "Leave request updated"),
            blocks=updated_blocks,
        )
    except Exception as e:
        logger.error(f"Failed to update message after approve: {e}")


@app.action("reject_leave_btn")
def handle_reject_leave(ack, body, client):
    """Handle Reject button click — open a modal for rejection reason."""
    ack()
    action = body["actions"][0]
    btn_data = json.loads(action["value"])

    # Include channel and message ts so the modal submission can update the original message
    modal_metadata = json.dumps({
        "request_id": btn_data["request_id"],
        "employee_id": btn_data["employee_id"],
        "role": btn_data["role"],
        "employee_name": btn_data.get("employee_name", "Employee"),
        "channel_id": body["channel"]["id"],
        "message_ts": body["message"]["ts"],
    })

    try:
        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": "reject_modal",
                "private_metadata": modal_metadata,
                "title": {"type": "plain_text", "text": "Reject Leave Request"},
                "submit": {"type": "plain_text", "text": "Reject"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"Rejecting leave request `{btn_data['request_id']}` for *{btn_data.get('employee_name', 'Employee')}*",
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "reject_reason_block",
                        "label": {"type": "plain_text", "text": "Reason for rejection"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "reject_reason_input",
                            "multiline": True,
                            "placeholder": {"type": "plain_text", "text": "Enter the reason for rejecting this leave request..."},
                        },
                    },
                ],
            },
        )
    except Exception as e:
        logger.error(f"Failed to open reject modal: {e}")


@app.view("reject_modal")
def handle_reject_modal(ack, body, client, view):
    """Handle reject modal submission — execute reject and update the original message."""
    ack()
    user_name = body["user"].get("real_name", body["user"].get("username", "Manager"))

    metadata = json.loads(view["private_metadata"])
    request_id = metadata["request_id"]
    employee_id = metadata["employee_id"]
    role = metadata["role"]
    emp_name = metadata.get("employee_name", "Employee")
    channel_id = metadata["channel_id"]
    message_ts = metadata["message_ts"]

    reason = view["state"]["values"]["reject_reason_block"]["reject_reason_input"]["value"]

    result = hrms_execute_tool(
        "reject_leave",
        {"request_id": request_id, "remarks": reason},
        employee_id,
        role,
    )

    if isinstance(result, dict) and not result.get("error"):
        # TODO: Map employee_id to Slack user ID for DM notifications
        logger.info(f"NOTIFICATION: {emp_name}'s leave request was rejected by {user_name}")

    # Fetch the original message to update it
    try:
        msg_resp = client.conversations_history(channel=channel_id, latest=message_ts, inclusive=True, limit=1)
        original_blocks = msg_resp["messages"][0].get("blocks", []) if msg_resp["messages"] else []
        original_text = msg_resp["messages"][0].get("text", "Leave request updated") if msg_resp["messages"] else "Leave request updated"
    except Exception as e:
        logger.error(f"Failed to fetch original message for reject update: {e}")
        return

    updated_blocks = []
    for block in original_blocks:
        if block.get("type") == "actions":
            elements = block.get("elements", [])
            matching = any(
                el.get("action_id") in ("approve_leave_btn", "reject_leave_btn")
                and _btn_matches_request(el, request_id)
                for el in elements
            )
            if matching:
                if isinstance(result, dict) and not result.get("error"):
                    updated_blocks.append({
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": f"Rejected by {user_name}: {reason}"}],
                    })
                else:
                    error_msg = result.get("error", "Unknown error") if isinstance(result, dict) else str(result)
                    updated_blocks.append({
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": f"Failed to reject: {error_msg}"}],
                    })
                continue
        updated_blocks.append(block)

    try:
        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text=original_text,
            blocks=updated_blocks,
        )
    except Exception as e:
        logger.error(f"Failed to update message after reject: {e}")


@app.action("confirm_apply_btn")
def handle_confirm_apply(ack, body, client):
    """Handle Submit Leave button click — apply the leave."""
    ack()
    action = body["actions"][0]
    btn_data = json.loads(action["value"])

    leave_details = btn_data["leave_details"]
    employee_id = btn_data["employee_id"]
    role = btn_data["role"]

    result = hrms_execute_tool("apply_leave", leave_details, employee_id, role)

    channel = body["channel"]["id"]
    message_ts = body["message"]["ts"]
    original_blocks = body["message"].get("blocks", [])

    # Replace the actions block with the result
    updated_blocks = []
    for block in original_blocks:
        if block.get("type") == "actions":
            elements = block.get("elements", [])
            matching = any(
                el.get("action_id") in ("confirm_apply_btn", "cancel_apply_btn")
                for el in elements
            )
            if matching:
                if isinstance(result, dict) and not result.get("error"):
                    updated_blocks.append({
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": "Leave request submitted successfully."}],
                    })
                else:
                    error_msg = result.get("error", "Unknown error") if isinstance(result, dict) else str(result)
                    updated_blocks.append({
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": f"Failed to submit leave: {error_msg}"}],
                    })
                continue
        updated_blocks.append(block)

    try:
        client.chat_update(
            channel=channel,
            ts=message_ts,
            text=body["message"].get("text", "Leave application updated"),
            blocks=updated_blocks,
        )
    except Exception as e:
        logger.error(f"Failed to update message after apply: {e}")


@app.action("cancel_apply_btn")
def handle_cancel_apply(ack, body, client):
    """Handle Cancel button click — cancel the leave application."""
    ack()
    channel = body["channel"]["id"]
    message_ts = body["message"]["ts"]
    original_blocks = body["message"].get("blocks", [])

    # Replace the actions block with a cancellation notice
    updated_blocks = []
    for block in original_blocks:
        if block.get("type") == "actions":
            elements = block.get("elements", [])
            matching = any(
                el.get("action_id") in ("confirm_apply_btn", "cancel_apply_btn")
                for el in elements
            )
            if matching:
                updated_blocks.append({
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": "Leave application cancelled."}],
                })
                continue
        updated_blocks.append(block)

    try:
        client.chat_update(
            channel=channel,
            ts=message_ts,
            text="Leave application cancelled.",
            blocks=updated_blocks,
        )
    except Exception as e:
        logger.error(f"Failed to update message after cancel: {e}")


def _btn_matches_request(element, request_id):
    """Check if a button element's value matches a given request_id."""
    try:
        data = json.loads(element.get("value", "{}"))
        return data.get("request_id") == request_id
    except (json.JSONDecodeError, TypeError):
        return False


# ── Start ──

if __name__ == "__main__":
    print("=" * 60)
    print("Gamyam HRMS — Slack Connector")
    print(f"API: {HRMS_API_URL}")
    print(f"Model: {OPENAI_MODEL}")
    print(f"Bot Token: {'set' if SLACK_BOT_TOKEN else 'MISSING'}")
    print(f"App Token: {'set' if SLACK_APP_TOKEN else 'MISSING'}")
    print(f"OpenAI: {'set' if OPENAI_API_KEY else 'MISSING'}")
    print("=" * 60)

    if not all([SLACK_BOT_TOKEN, SLACK_APP_TOKEN, OPENAI_API_KEY]):
        print("Missing env vars. Set SLACK_BOT_TOKEN, SLACK_APP_TOKEN, OPENAI_API_KEY")
        exit(1)

    try:
        r = requests.get(f'{HRMS_API_URL}/api/v1/leaves/policy/', timeout=5)
        print(f"HRMS API: reachable ({r.status_code})")
    except Exception as e:
        print(f"HRMS API: not reachable ({e})")

    print("Starting Socket Mode...")
    SocketModeHandler(app, SLACK_APP_TOKEN).start()
