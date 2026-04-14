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
import time
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

app = App(token=SLACK_BOT_TOKEN)
openai_client = OpenAI(api_key=OPENAI_API_KEY)


# ── Pipeline Config Cache ──

_pipeline_cache = {'data': None, 'ts': 0}


def _get_pipeline_config():
    now = time.time()
    if _pipeline_cache['data'] and (now - _pipeline_cache['ts']) < 60:
        return _pipeline_cache['data']
    try:
        resp = requests.get(f'{HRMS_API_URL}/api/v1/bot/config/', timeout=5)
        if resp.status_code == 200:
            _pipeline_cache['data'] = resp.json()
            _pipeline_cache['ts'] = now
    except Exception as e:
        logger.warning(f"Failed to fetch pipeline config: {e}")
    return _pipeline_cache.get('data')


# ── LLM Client Helper ──

_llm_clients = {}


def _get_llm_client(provider_config):
    if not provider_config:
        return openai_client
    key = provider_config.get('api_url', '') or 'openai'
    if key not in _llm_clients:
        if provider_config['provider_type'] == 'openai':
            _llm_clients[key] = openai_client
        else:
            _llm_clients[key] = OpenAI(api_key='not-needed', base_url=provider_config['api_url'])
    return _llm_clients[key]


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

    config = _get_pipeline_config()
    if not config or not config.get('pipeline'):
        return f"You are an HRMS assistant. Today: {today}."

    for step in config['pipeline']['steps']:
        if step['step_type'] == 'system_prompt' and step.get('role_filter') == role:
            if step.get('prompt') and step['prompt'].get('template'):
                template = step['prompt']['template']
                try:
                    prompt = template.format(
                        name=name, emp_id=emp_id, dept=dept_name,
                        designation=desg_name, manager=mgr_name,
                        today=today, leave_year=leave_year,
                        next_year=next_year, role=role,
                    )
                except KeyError:
                    continue

                # For admin, add dynamic context about configured leave types
                if role == 'ADMIN':
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

    return f"You are an HRMS assistant. Today: {today}."


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


# ── Pipeline Step Executors ──

def _execute_classify_step(step, text, role):
    """Execute a classify step. Returns the intent string."""
    client = _get_llm_client(step.get('llm_provider'))
    model = step['llm_provider']['model_id'] if step.get('llm_provider') else OPENAI_MODEL
    config = step.get('config', {})
    template = step.get('prompt', {}).get('template', '')

    prompt = template.format(
        role=role, user_message=text,
        name='', emp_id='', dept='', designation='',
        manager='', today=date.today().isoformat(),
        leave_year='2026', tool_results='', previous_output='',
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=config.get('max_tokens', 20),
        temperature=config.get('temperature', 0),
    )
    return resp.choices[0].message.content.strip().upper().replace(' ', '_')


def _execute_reply_step(step, messages, session):
    """Execute a reply step (all-in-one tool call + reply loop). Returns (reply, tool_calls_log)."""
    client = _get_llm_client(step.get('llm_provider'))
    model = step['llm_provider']['model_id'] if step.get('llm_provider') else OPENAI_MODEL
    config = step.get('config', {})
    tool_calls_log = []

    for _ in range(config.get('max_rounds', 10)):
        resp = client.chat.completions.create(
            model=model, messages=messages,
            tools=session['openai_tools'] or None,
            tool_choice=config.get('tool_choice', 'auto') if session['openai_tools'] else None,
        )
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
                tool_calls_log.append({"tool": fname, "args": fargs, "result": result})
            continue
        return msg.content or "(no response)", tool_calls_log

    return "Too many tool rounds.", tool_calls_log


def _execute_plan_step(step, text, intent, role, session):
    """Execute a plan step. Returns list of planned tool calls."""
    client = _get_llm_client(step.get('llm_provider'))
    model = step['llm_provider']['model_id'] if step.get('llm_provider') else OPENAI_MODEL
    config = step.get('config', {})
    template = step.get('prompt', {}).get('template', '')
    tool_names = [t['name'] for t in session['tools']]

    prompt = template.format(
        role=role, user_message=text, intent=intent,
        tool_names=', '.join(tool_names), today=date.today().isoformat(),
        name='', emp_id='', dept='', designation='', manager='',
        leave_year='2026', tool_results='', previous_output='',
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=config.get('max_tokens', 500),
        temperature=config.get('temperature', 0),
    )
    content = resp.choices[0].message.content.strip()
    # Extract JSON from possible markdown code block
    if '```' in content:
        content = content.split('```')[1]
        if content.startswith('json'):
            content = content[4:]
        content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse tool plan: {content[:200]}")
        return []


def _execute_tool_call_step(step, plan, employee_id, role):
    """Execute tool calls from a plan with error retry. Returns tool_calls_log."""
    config = step.get('config', {})
    retry = config.get('retry_on_error', True)
    max_retries = config.get('max_retries', 3)
    fix_template = step.get('prompt', {}).get('template', '')
    tool_calls_log = []

    for planned in plan:
        tool_name = planned.get('tool', '')
        args = planned.get('args', {})

        for attempt in range(max_retries if retry else 1):
            result = hrms_execute_tool(tool_name, args, employee_id, role)
            logger.info(f"Tool: {tool_name}({json.dumps(args)[:150]}) -> {json.dumps(result, default=str)[:200]}")

            if not isinstance(result, dict) or 'error' not in result:
                break  # Success

            if attempt < (max_retries - 1) and retry and fix_template:
                # Ask LLM to fix args
                try:
                    client = _get_llm_client(step.get('llm_provider'))
                    model = step['llm_provider']['model_id'] if step.get('llm_provider') else OPENAI_MODEL
                    fix_prompt = fix_template.format(
                        tool_name=tool_name, error=result['error'],
                        tool_results=json.dumps(args),
                        user_message='', name='', emp_id='', dept='', designation='',
                        manager='', today='', leave_year='', role='', previous_output='',
                    )
                    fix_resp = client.chat.completions.create(
                        model=model, messages=[{"role": "user", "content": fix_prompt}],
                        max_tokens=200, temperature=0,
                    )
                    fixed = fix_resp.choices[0].message.content.strip()
                    if '```' in fixed:
                        fixed = fixed.split('```')[1]
                        if fixed.startswith('json'):
                            fixed = fixed[4:]
                        fixed = fixed.strip()
                    args = json.loads(fixed)
                    logger.info(f"Retry {tool_name} with fixed args: {json.dumps(args)[:200]}")
                except Exception:
                    pass

        tool_calls_log.append({"tool": tool_name, "args": args, "result": result})

    return tool_calls_log


def _execute_generate_step(step, text, tool_calls_log, session, feedback=None):
    """Generate response from tool results."""
    client = _get_llm_client(step.get('llm_provider'))
    model = step['llm_provider']['model_id'] if step.get('llm_provider') else OPENAI_MODEL
    config = step.get('config', {})
    template = step.get('prompt', {}).get('template', '')

    tool_results_str = "\n".join(
        f"{tc['tool']}: {json.dumps(tc['result'], default=str)[:500]}"
        for tc in tool_calls_log)

    feedback_line = f"\nFEEDBACK: {feedback}\nFix the issues above.\n" if feedback else ""

    prompt = template.format(
        user_message=text, tool_results=tool_results_str or "(no tools called)",
        name=session.get('name', 'User'), role=session.get('role', 'EMPLOYEE'),
        previous_output=feedback_line,
        emp_id='', dept='', designation='', manager='',
        today=date.today().isoformat(), leave_year='2026',
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": session['system_prompt']},
                  {"role": "user", "content": prompt}],
        max_tokens=config.get('max_tokens', 500),
    )
    return resp.choices[0].message.content or "(no response)"


def _execute_validate_step(step, text, tool_calls_log, response):
    """Review response quality. Returns (approved, feedback)."""
    client = _get_llm_client(step.get('llm_provider'))
    model = step['llm_provider']['model_id'] if step.get('llm_provider') else OPENAI_MODEL
    config = step.get('config', {})
    template = step.get('prompt', {}).get('template', '')

    tool_results_str = "\n".join(
        f"{tc['tool']}: {json.dumps(tc['result'], default=str)[:500]}"
        for tc in tool_calls_log)

    prompt = template.format(
        user_message=text, tool_results=tool_results_str,
        previous_output=response,
        name='', emp_id='', dept='', designation='', manager='',
        today='', leave_year='', role='',
    )

    resp = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}],
        max_tokens=100, temperature=config.get('temperature', 0),
    )

    verdict = resp.choices[0].message.content.strip()
    if verdict.startswith("APPROVED"):
        return True, None
    elif verdict.startswith("REDO"):
        return False, verdict[5:].strip().lstrip(':').strip()
    return True, None


# ── Conversation Engine ──

def process_message(uid, text):
    session = get_session(uid)
    if not session['employee_id']:
        return ("Set a role first:\n• `/employee GIT-001` — login as employee\n"
                "• `/hr` — login as HR admin\n• `/manager GIT-023` — login as manager\n\n"
                "IDs: `GIT-001` Prithvi, `GIT-002` Meena, `GIT-023` Chandrakala, `GIT-046` Bhavishya"), None

    session['conversation'].append({"role": "user", "content": text})
    messages = [{"role": "system", "content": session['system_prompt']}] + session['conversation']

    config = _get_pipeline_config()
    if not config or not config.get('pipeline'):
        # No pipeline configured — fall back to simple GPT-4o loop
        logger.warning("No pipeline config available, using fallback GPT-4o loop")
        tool_calls_log = []
        for _ in range(10):
            try:
                resp = openai_client.chat.completions.create(
                    model=OPENAI_MODEL, messages=messages,
                    tools=session['openai_tools'] or None,
                    tool_choice="auto" if session['openai_tools'] else None,
                )
            except Exception as e:
                return f"LLM error: {e}", None
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
                    tool_calls_log.append({"tool": fname, "args": fargs, "result": result})
                continue
            reply = msg.content or "(no response)"
            blocks = _build_response(reply, tool_calls_log, session['employee_id'], session['role'])
            session['conversation'].append({"role": "assistant", "content": reply})
            if len(session['conversation']) > 40:
                keep = [m for m in session['conversation'][:-30] if isinstance(m, dict) and m.get('role') == 'tool']
                session['conversation'] = keep + session['conversation'][-30:]
            return reply, blocks
        return "Too many tool rounds. Try rephrasing.", None

    steps = config['pipeline']['steps']
    role = session['role']

    # Filter steps for this role (include steps with no role_filter or matching role)
    active_steps = [s for s in steps if not s.get('role_filter') or s.get('role_filter') == role]

    ctx = {'intent': None, 'path': 'simple', 'plan': [], 'tool_calls_log': [], 'reply': None}

    for step in active_steps:
        step_type = step['step_type']

        if step_type == 'system_prompt':
            continue  # Already handled in build_system_prompt

        elif step_type == 'classify':
            try:
                ctx['intent'] = _execute_classify_step(step, text, role)
                logger.info(f"Pipeline: intent={ctx['intent']}")
                simple_intents = set(step.get('config', {}).get('simple_intents', []))
                complex_intents = set(step.get('config', {}).get('complex_intents', []))
                if ctx['intent'] in complex_intents:
                    ctx['path'] = 'complex'
                else:
                    ctx['path'] = 'simple'
                logger.info(f"Pipeline: path={ctx['path']}")
            except Exception as e:
                logger.error(f"Classify failed: {e}")
                ctx['path'] = 'simple'

        elif step_type == 'reply':
            # Only run if path matches
            if step.get('config', {}).get('for_path', '') and step['config']['for_path'] != ctx['path']:
                continue
            try:
                ctx['reply'], ctx['tool_calls_log'] = _execute_reply_step(step, messages, session)
            except Exception as e:
                logger.error(f"Reply step failed: {e}")
                ctx['reply'] = "Sorry, I encountered an error processing your request."
            break  # reply step produces final output

        elif step_type == 'plan':
            if step.get('config', {}).get('for_path', '') and step['config']['for_path'] != ctx['path']:
                continue
            try:
                ctx['plan'] = _execute_plan_step(step, text, ctx['intent'], role, session)
                logger.info(f"Pipeline: planned {len(ctx['plan'])} tool calls")
            except Exception as e:
                logger.error(f"Planning failed: {e}, falling back to simple")
                # Find the reply step and use it
                for fallback in active_steps:
                    if fallback['step_type'] == 'reply':
                        try:
                            ctx['reply'], ctx['tool_calls_log'] = _execute_reply_step(fallback, messages, session)
                        except Exception as e2:
                            logger.error(f"Fallback reply step also failed: {e2}")
                            ctx['reply'] = "Sorry, I encountered an error processing your request."
                        break
                break

        elif step_type == 'tool_call':
            if step.get('config', {}).get('for_path', '') and step['config']['for_path'] != ctx['path']:
                continue
            try:
                if ctx['plan']:
                    ctx['tool_calls_log'] = _execute_tool_call_step(step, ctx['plan'], session['employee_id'], role)
            except Exception as e:
                logger.error(f"Tool call step failed: {e}")

        elif step_type == 'generate':
            if step.get('config', {}).get('for_path', '') and step['config']['for_path'] != ctx['path']:
                continue
            try:
                ctx['reply'] = _execute_generate_step(step, text, ctx['tool_calls_log'], session)
            except Exception as e:
                logger.error(f"Generate step failed: {e}")
                ctx['reply'] = "Sorry, I encountered an error generating a response."

        elif step_type == 'validate':
            if step.get('config', {}).get('for_path', '') and step['config']['for_path'] != ctx['path']:
                continue
            if ctx['reply']:
                max_retries = step.get('config', {}).get('max_retries', 1)
                for _ in range(max_retries):
                    try:
                        approved, feedback = _execute_validate_step(step, text, ctx['tool_calls_log'], ctx['reply'])
                        if approved:
                            break
                        # Find generate step and regenerate
                        for gen_step in active_steps:
                            if gen_step['step_type'] == 'generate':
                                if gen_step.get('config', {}).get('for_path', '') and gen_step['config']['for_path'] != ctx['path']:
                                    continue
                                try:
                                    ctx['reply'] = _execute_generate_step(gen_step, text, ctx['tool_calls_log'], session, feedback=feedback)
                                except Exception as e:
                                    logger.error(f"Regenerate after validation failed: {e}")
                                break
                    except Exception as e:
                        logger.error(f"Validate step failed: {e}")
                        break

    reply = ctx['reply']
    if reply is None:
        reply = "Sorry, I couldn't process your request."

    blocks = _build_response(reply, ctx['tool_calls_log'], session['employee_id'], role)

    session['conversation'].append({"role": "assistant", "content": reply})
    if len(session['conversation']) > 40:
        keep = [m for m in session['conversation'][:-30] if isinstance(m, dict) and m.get('role') == 'tool']
        session['conversation'] = keep + session['conversation'][-30:]

    return reply, blocks


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
