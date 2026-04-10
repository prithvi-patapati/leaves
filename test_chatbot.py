"""
End-to-end chatbot integration test.
Uses OpenAI function calling with our MCP tool schemas.
Runs against the seeded Django database.
"""
import os
import sys
import json
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from test_config import OPENAI_API_KEY
from openai import OpenAI
from mcp_server.registry import get_tools_for_role
from mcp_server.executor import execute_tool
from employees.models import Employee

client = OpenAI(api_key=OPENAI_API_KEY)


def load_prompt(role, employee):
    from datetime import date
    today = date.today()
    leave_year = today.year if today.month >= 4 else today.year - 1

    return f"""You are Gamyam's HRMS assistant. You are talking to {employee.full_name} ({employee.employee_id}),
a {employee.designation.title} in {employee.department.name}.
Their reporting manager is {employee.reporting_manager.full_name if employee.reporting_manager else 'N/A'}.
Today is {today}. Leave year: {leave_year} (April {leave_year} - March {leave_year + 1}).
Use the provided tools to help them. Always check balance before applying leave.
For any write action, generate an idempotency_key using format: {employee.employee_id}_action_timestamp."""


def convert_tools_to_openai_format(tools):
    openai_tools = []
    for tool in tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"]
            }
        })
    return openai_tools


def run_conversation(employee_id, role, messages_to_send):
    employee = Employee.objects.get(employee_id=employee_id)
    system_prompt = load_prompt(role, employee)
    tools = get_tools_for_role(role)
    openai_tools = convert_tools_to_openai_format(tools)

    conversation = [{"role": "system", "content": system_prompt}]
    log = []

    for user_msg in messages_to_send:
        print(f"\n{'='*60}")
        print(f"USER ({employee.full_name}): {user_msg}")
        print(f"{'='*60}")

        conversation.append({"role": "user", "content": user_msg})

        max_iterations = 10
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            response = client.chat.completions.create(
                model="gpt-4o",
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

                    print(f"\n  TOOL CALL: {fname}")
                    print(f"  ARGS: {json.dumps(fargs, indent=2)}")

                    try:
                        result = execute_tool(
                            fname, fargs,
                            {'employee_id': employee_id, 'role': role}
                        )
                        result_str = json.dumps(result, indent=2, default=str)
                    except Exception as e:
                        result_str = json.dumps({"error": str(e)})

                    print(f"  RESULT: {result_str[:500]}")

                    conversation.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_str
                    })

                    log.append({
                        "tool": fname,
                        "args": fargs,
                        "result": result_str[:500]
                    })

                continue

            assistant_msg = msg.content
            print(f"\nASSISTANT: {assistant_msg}")
            conversation.append({"role": "assistant", "content": assistant_msg})
            log.append({"assistant": assistant_msg})
            break

    return log


def test_employee_check_balance():
    print("\n" + "="*80)
    print("TEST 1: Employee checks balance")
    print("="*80)
    run_conversation("GIT-001", "EMPLOYEE", [
        "What is my leave balance?"
    ])


def test_employee_apply_leave():
    print("\n" + "="*80)
    print("TEST 2: Employee applies for sick leave")
    print("="*80)
    run_conversation("GIT-001", "EMPLOYEE", [
        "I was unwell yesterday and today. Can you apply sick leave for April 9 and 10?"
    ])


def test_employee_plan_vacation():
    print("\n" + "="*80)
    print("TEST 3: Employee plans vacation")
    print("="*80)
    run_conversation("GIT-002", "EMPLOYEE", [
        "I want to take a week off in May for a family vacation. What are my options?"
    ])


def test_manager_approve():
    print("\n" + "="*80)
    print("TEST 4: Manager approves leave")
    print("="*80)
    run_conversation("GIT-023", "MANAGER", [
        "Show me pending requests from my team.",
        "Approve all pending requests."
    ])


def test_hr_check_balance_for_employee():
    print("\n" + "="*80)
    print("TEST 5: HR checks employee balance")
    print("="*80)
    run_conversation("GIT-046", "ADMIN", [
        "What is Prithvi's (GIT-001) leave balance?"
    ])


def test_hr_create_override():
    print("\n" + "="*80)
    print("TEST 6: HR creates override")
    print("="*80)
    run_conversation("GIT-046", "ADMIN", [
        "Block WFH for GIT-001 for the month of May 2026. He's on a PIP."
    ])


def test_hr_update_policy():
    print("\n" + "="*80)
    print("TEST 7: HR updates policy")
    print("="*80)
    run_conversation("GIT-046", "ADMIN", [
        "Increase sick leave from 8 to 10 days for everyone. Make it retroactive."
    ])


def test_hr_add_employee():
    print("\n" + "="*80)
    print("TEST 8: HR adds new employee")
    print("="*80)
    run_conversation("GIT-046", "ADMIN", [
        "Add a new employee: Raj Verma, ID GIT-077, raj.verma@gamyam.co, male, Software Developer in Engineering, reports to Chandrakala (GIT-023). Full time, joined today April 10 2026."
    ])


def test_employee_policy_inquiry():
    print("\n" + "="*80)
    print("TEST 9: Employee asks about policies")
    print("="*80)
    run_conversation("GIT-020", "EMPLOYEE", [
        "What is the WFH policy? How many days do I get?"
    ])


def test_hr_adjust_balance():
    print("\n" + "="*80)
    print("TEST 10: HR adjusts balance")
    print("="*80)
    run_conversation("GIT-046", "ADMIN", [
        "Give Meena (GIT-002) 2 extra earned leave days because she worked on Diwali weekend."
    ])


if __name__ == "__main__":
    print("="*80)
    print("GAMYAM HRMS — CHATBOT INTEGRATION TEST")
    print("Testing with OpenAI function calling against live Django backend")
    print("="*80)

    tests = [
        test_employee_check_balance,
        test_employee_apply_leave,
        test_employee_plan_vacation,
        test_manager_approve,
        test_hr_check_balance_for_employee,
        test_hr_create_override,
        test_hr_update_policy,
        test_hr_add_employee,
        test_employee_policy_inquiry,
        test_hr_adjust_balance,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
            print(f"\n  >> PASSED")
        except Exception as e:
            failed += 1
            print(f"\n  >> FAILED: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*80}")
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'='*80}")
