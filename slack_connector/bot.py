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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('slack_connector')

sessions = {}

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


def _normalize(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def resolve_employee_input(text):
    """Resolve flexible input to (employee_id, error_message).

    Accepts: GIT-001, 001, 1, Prithvi, prithvi, pritvi (typo), etc.
    Returns: (employee_id, None) on match, (None, suggestion_message) on failure.
    """
    raw = text.strip().strip('`').strip()
    if not raw:
        return None, "Please provide an employee ID or name."

    # Try exact ID match first (e.g., GIT-001)
    candidate = raw.upper().replace(' ', '')
    emp = hrms_get_employee(candidate)
    if emp:
        return emp['employee_id'], None

    # Try with GIT- prefix if they typed just a number (e.g., 1, 01, 001, 23)
    digits = re.sub(r'[^0-9]', '', raw)
    if digits:
        padded = f"GIT-{digits.zfill(3)}"
        emp = hrms_get_employee(padded)
        if emp:
            return emp['employee_id'], None

    # Load all employees for name/fuzzy matching
    all_emps = hrms_get_all_employees()
    if not all_emps:
        return None, f"Could not find `{raw}` and employee list is unavailable."

    query = _normalize(raw)

    # Exact name match (case-insensitive)
    for e in all_emps:
        if _normalize(e.get('full_name', '')) == query:
            return e['employee_id'], None
        # Match on first name
        first = e.get('full_name', '').split()[0] if e.get('full_name') else ''
        if first and _normalize(first) == query:
            return e['employee_id'], None

    # Substring match
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

    # Fuzzy match: find names that share enough characters (handle typos)
    def similarity(a, b):
        common = sum(1 for c in set(a) if c in b)
        return (2.0 * common) / (len(set(a)) + len(set(b))) if a and b else 0

    scored = []
    for e in all_emps:
        name = e.get('full_name', '')
        # Check against full name and first name
        full_sim = similarity(query, _normalize(name))
        first_name = name.split()[0] if name else ''
        first_sim = similarity(query, _normalize(first_name))
        best = max(full_sim, first_sim)
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

    base = f"Today: {today}. Leave year: 2026 (April 2026 - March 2027).\n"

    if role == 'ADMIN':
        return (f"You are Gamyam's HRMS assistant for HR administrators.\n"
                f"Talking to: {name} ({emp_id}), HR Admin.\n{base}"
                f"You have FULL access to all tools. Confirm before destructive actions. "
                f"Ask prospective vs retroactive on entitlement changes. Check for override conflicts. "
                f"Generate idempotency_key as HR_{emp_id}_action_{today}_xxxx.")

    elif role == 'MANAGER':
        return (f"You are Gamyam's HRMS assistant for managers.\n"
                f"Talking to: {name} ({emp_id}), {desg_name} in {dept_name}.\n{base}"
                f"You can view/approve/reject team requests and apply your own leaves. "
                f"Show details before approving. Require reason for rejections. "
                f"Generate idempotency_key as MGR_{emp_id}_action_{today}_xxxx.")

    else:
        return (f"You are Gamyam's HRMS assistant for employees.\n"
                f"Talking to: {name} ({emp_id}), {desg_name} in {dept_name}. Manager: {mgr_name}.\n{base}"
                f"Always check balance before applying. Run validate_leave before apply_leave. "
                f"Confirm with user before submitting. Explain policies simply. "
                f"Generate idempotency_key as {emp_id}_action_{today}_xxxx.")


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


# ── Conversation Engine ──

def process_message(uid, text):
    session = get_session(uid)
    if not session['employee_id']:
        return ("Set a role first:\n• `/employee GIT-001` — login as employee\n"
                "• `/hr` — login as HR admin\n• `/manager GIT-023` — login as manager\n\n"
                "IDs: `GIT-001` Prithvi, `GIT-002` Meena, `GIT-023` Chandrakala, `GIT-046` Bhavishya")

    session['conversation'].append({"role": "user", "content": text})
    messages = [{"role": "system", "content": session['system_prompt']}] + session['conversation']

    for _ in range(10):
        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4o", messages=messages,
                tools=session['openai_tools'] or None,
                tool_choice="auto" if session['openai_tools'] else None,
            )
        except Exception as e:
            return f"LLM error: {e}"

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
            continue

        reply = msg.content or "(no response)"
        session['conversation'].append({"role": "assistant", "content": reply})
        if len(session['conversation']) > 40:
            session['conversation'] = session['conversation'][-20:]
        return reply

    return "Too many tool rounds. Try rephrasing."


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
    say(process_message(event['user'], text))


@app.event("app_mention")
def on_mention(event, say):
    text = re.sub(r'<@[A-Z0-9]+>\s*', '', event.get('text', '')).strip()
    if not text:
        say("Use `/employee GIT-001`, `/hr`, or `/manager GIT-023` to set your role, then chat with me.")
        return
    say(process_message(event['user'], text))


# ── Start ──

if __name__ == "__main__":
    print("=" * 60)
    print("Gamyam HRMS — Slack Connector")
    print(f"API: {HRMS_API_URL}")
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
        print(f"HRMS API: not reachable ({e}) — bot will start but tools will fail")

    print("Starting Socket Mode...")
    SocketModeHandler(app, SLACK_APP_TOKEN).start()
