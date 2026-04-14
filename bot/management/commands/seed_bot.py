from django.core.management.base import BaseCommand
from bot.models import Bot, LLMProvider, Pipeline, PipelineStep, Prompt


EMPLOYEE_PROMPT = """You are Gamyam's HRMS leave management assistant for employees.
Talking to: {name} ({emp_id}), {designation} in {dept}. Manager: {manager}.
Today: {today}. Leave year: {leave_year} (April {leave_year} - March next year).

You can help with: checking leave balance, applying for leave, cancelling leave, explaining policies, viewing optional holidays.

IMPORTANT RULES:
- NEVER make up data. Only state facts from tool results.
- Always check balance before applying. Run validate_leave before apply_leave.
- Confirm with user before submitting any leave request.
- Use leave type CODES: SL=Sick, PL=Planned/Casual, EL=Earned, LOP=Loss of Pay, WFH=Work From Home, BL=Bereavement, ML=Maternity, PtL=Paternity, OH=Optional Holiday.
- Be concise and helpful.
- Generate idempotency_key as {emp_id}_action_{today}_xxxx."""

MANAGER_PROMPT = """You are Gamyam's HRMS leave management assistant for managers.
Talking to: {name} ({emp_id}), {designation} in {dept}.
Today: {today}. Leave year: {leave_year} (April {leave_year} - March next year).

You can: view/approve/reject team leave requests, check team balances and calendar, apply for your own leaves.
When showing pending requests, include: employee name, leave type, dates, reason, request ID.
The 'id' field from get_team_requests is the request_id for approve/reject.

IMPORTANT RULES:
- NEVER make up data. Only state facts from tool results.
- Show details before approving. Require reason for rejections.
- Use leave type CODES: SL, PL, EL, LOP, WFH, BL, ML, PtL, OH.
- Generate idempotency_key as MGR_{emp_id}_action_{today}_xxxx."""

ADMIN_PROMPT = """You are Gamyam's HRMS leave management assistant for HR administrators.
Talking to: {name} ({emp_id}), HR Admin.
Today: {today}. Leave year: {leave_year} (April {leave_year} - March next year).

You have access to 48 tools for managing the entire HRMS system:
- Leave policy: create/update/deactivate leave types, view policies
- Employee management: add/update/transfer/deactivate employees, search
- Leave operations: view all requests, adjust balances, create overrides, bulk operations
- Organization: departments, teams, HR actions
- System: trigger bulk credit, monthly accrual, year-end processing

IMPORTANT RULES:
- NEVER make up data. Only state facts from tool results.
- If tool results are empty, say so clearly (e.g. 'No leave types configured yet.').
- Use leave type CODES: SL=Sick, PL=Planned/Casual, EL=Earned, LOP=Loss of Pay, WFH=Work From Home, BL=Bereavement, ML=Maternity, PtL=Paternity, OH=Optional Holiday.
- Confirm before destructive actions.
- Generate idempotency_key as HR_{emp_id}_action_{today}_xxxx."""


class Command(BaseCommand):
    help = 'Seed default bot configuration'

    def handle(self, *args, **options):
        # LLM Providers
        gpt4o, c = LLMProvider.objects.get_or_create(
            model_id='gpt-4o',
            defaults={'name': 'GPT-4o', 'provider_type': 'openai', 'is_active': True,
                      'description': 'OpenAI GPT-4o'})
        self.stdout.write(f"  {'Created' if c else 'Exists'}: LLMProvider GPT-4o")

        xlam, c = LLMProvider.objects.get_or_create(
            model_id='xlam',
            defaults={'name': 'xLAM-2-1B', 'provider_type': 'local', 'is_active': False,
                      'api_url': 'http://host.docker.internal:8081/v1',
                      'description': 'Local xLAM for tool calling'})
        self.stdout.write(f"  {'Created' if c else 'Exists'}: LLMProvider xLAM-2-1B")

        gemma, c = LLMProvider.objects.get_or_create(
            model_id='gemma',
            defaults={'name': 'Gemma-3-1B', 'provider_type': 'local', 'is_active': False,
                      'api_url': 'http://host.docker.internal:8082/v1',
                      'description': 'Local Gemma for replies'})
        self.stdout.write(f"  {'Created' if c else 'Exists'}: LLMProvider Gemma-3-1B")

        # Prompts
        emp_prompt, c = Prompt.objects.get_or_create(
            name='Employee System Prompt',
            defaults={'template': EMPLOYEE_PROMPT, 'is_active': True,
                      'description': 'System prompt for employee role'})
        self.stdout.write(f"  {'Created' if c else 'Exists'}: Prompt Employee")

        mgr_prompt, c = Prompt.objects.get_or_create(
            name='Manager System Prompt',
            defaults={'template': MANAGER_PROMPT, 'is_active': True,
                      'description': 'System prompt for manager role'})
        self.stdout.write(f"  {'Created' if c else 'Exists'}: Prompt Manager")

        admin_prompt, c = Prompt.objects.get_or_create(
            name='Admin System Prompt',
            defaults={'template': ADMIN_PROMPT, 'is_active': True,
                      'description': 'System prompt for HR admin role'})
        self.stdout.write(f"  {'Created' if c else 'Exists'}: Prompt Admin")

        # Pipeline
        pipeline, c = Pipeline.objects.get_or_create(
            name='Default GPT-4o Pipeline',
            defaults={'is_active': True,
                      'description': 'GPT-4o handles system prompt, tool calls, and reply in one flow.'})
        self.stdout.write(f"  {'Created' if c else 'Exists'}: Pipeline")

        # Pipeline Steps
        # Step 0: System prompts per role
        PipelineStep.objects.get_or_create(
            pipeline=pipeline, order=0, role_filter='EMPLOYEE',
            defaults={'name': 'Employee System Prompt', 'step_type': 'system_prompt',
                      'prompt': emp_prompt, 'is_active': True})
        PipelineStep.objects.get_or_create(
            pipeline=pipeline, order=1, role_filter='MANAGER',
            defaults={'name': 'Manager System Prompt', 'step_type': 'system_prompt',
                      'prompt': mgr_prompt, 'is_active': True})
        PipelineStep.objects.get_or_create(
            pipeline=pipeline, order=2, role_filter='ADMIN',
            defaults={'name': 'Admin System Prompt', 'step_type': 'system_prompt',
                      'prompt': admin_prompt, 'is_active': True})
        self.stdout.write(f"  Created/Exists: 3 System Prompt steps")

        # Step 3: Tool calling + reply (GPT-4o does both)
        PipelineStep.objects.get_or_create(
            pipeline=pipeline, order=10,
            defaults={'name': 'GPT-4o Tool Call + Reply', 'step_type': 'tool_call',
                      'llm_provider': gpt4o, 'is_active': True,
                      'config': {'tool_choice': 'auto', 'max_rounds': 10}})
        self.stdout.write(f"  Created/Exists: Tool Call step")

        # Bot
        Bot.objects.get_or_create(
            name='HRMS Slack Bot',
            defaults={'connector_type': 'slack', 'status': 'active', 'pipeline': pipeline,
                      'description': 'Main HRMS leave management Slack bot'})
        self.stdout.write(f"  Created/Exists: Bot")

        self.stdout.write(self.style.SUCCESS('Bot config seeded!'))
