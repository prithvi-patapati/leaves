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


def set_role(uid, employee_id, role):
    session = get_session(uid)
    emp = hrms_get_employee(employee_id)
    if not emp:
        return f"Could not find employee `{employee_id}`. Check the ID and ensure the API is running at `{HRMS_API_URL}`."

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
        say("Usage: `/employee GIT-001`\n\nIDs: `GIT-001` Prithvi, `GIT-002` Meena, "
            "`GIT-020` Rohit, `GIT-053` Akshay (probation)")
        return
    say(set_role(command['user_id'], text.upper(), 'EMPLOYEE'))


@app.command("/hr")
def cmd_hr(ack, command, say):
    ack()
    text = command.get('text', '').strip()
    emp_id = text.upper() if text else 'GIT-046'
    say(set_role(command['user_id'], emp_id, 'ADMIN'))


@app.command("/manager")
def cmd_manager(ack, command, say):
    ack()
    text = command.get('text', '').strip()
    if not text:
        say("Usage: `/manager GIT-023`\n\nIDs: `GIT-023` Chandrakala (47 reports), "
            "`GIT-008` Dinesh, `GIT-046` Bhavishya")
        return
    say(set_role(command['user_id'], text.upper(), 'MANAGER'))


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
