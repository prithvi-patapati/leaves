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
    help = 'Seed default bot configuration data (LLM providers, bot, prompts, pipeline)'

    def handle(self, *args, **options):
        self.stdout.write('Seeding bot configuration...')

        # --- LLM Providers ---
        gpt4o, created = LLMProvider.objects.get_or_create(
            model_id='gpt-4o',
            defaults={
                'name': 'GPT-4o',
                'provider_type': 'openai',
                'api_url': '',
                'is_active': True,
                'description': 'OpenAI GPT-4o model',
            },
        )
        action = 'Created' if created else 'Already exists'
        self.stdout.write(f'  {action}: LLMProvider "GPT-4o"')

        xlam, created = LLMProvider.objects.get_or_create(
            model_id='xlam',
            defaults={
                'name': 'xLAM-2-1B',
                'provider_type': 'local',
                'api_url': 'http://host.docker.internal:8081/v1',
                'is_active': False,
                'description': 'Local xLAM-2-1B model for tool calling',
            },
        )
        action = 'Created' if created else 'Already exists'
        self.stdout.write(f'  {action}: LLMProvider "xLAM-2-1B"')

        gemma, created = LLMProvider.objects.get_or_create(
            model_id='gemma',
            defaults={
                'name': 'Gemma-3-1B',
                'provider_type': 'local',
                'api_url': 'http://host.docker.internal:8082/v1',
                'is_active': False,
                'description': 'Local Gemma-3-1B model for reply generation',
            },
        )
        action = 'Created' if created else 'Already exists'
        self.stdout.write(f'  {action}: LLMProvider "Gemma-3-1B"')

        # --- Bot ---
        bot, created = Bot.objects.get_or_create(
            name='HRMS Slack Bot',
            defaults={
                'connector_type': 'slack',
                'status': 'active',
                'llm_provider': gpt4o,
                'description': 'Main HRMS leave management Slack bot',
                'config': {},
            },
        )
        action = 'Created' if created else 'Already exists'
        self.stdout.write(f'  {action}: Bot "HRMS Slack Bot"')

        # --- Prompts ---
        prompts_data = [
            {
                'name': 'Employee System Prompt',
                'role': 'EMPLOYEE',
                'template': EMPLOYEE_PROMPT,
                'description': 'System prompt for employees interacting with the HRMS bot.',
            },
            {
                'name': 'Manager System Prompt',
                'role': 'MANAGER',
                'template': MANAGER_PROMPT,
                'description': 'System prompt for managers interacting with the HRMS bot.',
            },
            {
                'name': 'Admin System Prompt',
                'role': 'ADMIN',
                'template': ADMIN_PROMPT,
                'description': 'System prompt for HR administrators interacting with the HRMS bot.',
            },
        ]

        for prompt_data in prompts_data:
            prompt, created = Prompt.objects.get_or_create(
                name=prompt_data['name'],
                defaults={
                    'role': prompt_data['role'],
                    'template': prompt_data['template'],
                    'is_active': True,
                    'version': 1,
                    'description': prompt_data['description'],
                },
            )
            action = 'Created' if created else 'Already exists'
            self.stdout.write(f'  {action}: Prompt "{prompt_data["name"]}"')

        # --- Pipeline ---
        pipeline, created = Pipeline.objects.get_or_create(
            bot=bot,
            name='Default Pipeline',
            defaults={
                'is_active': True,
                'description': 'Default single-step pipeline using GPT-4o for tool calling and reply.',
            },
        )
        action = 'Created' if created else 'Already exists'
        self.stdout.write(f'  {action}: Pipeline "Default Pipeline"')

        # --- Pipeline Step ---
        step, created = PipelineStep.objects.get_or_create(
            pipeline=pipeline,
            order=1,
            defaults={
                'name': 'Unified GPT-4o',
                'step_type': 'tool_call',
                'llm_provider': gpt4o,
                'prompt_override': '',
                'config': {
                    'tool_choice': 'auto',
                    'max_rounds': 10,
                },
                'is_active': True,
            },
        )
        action = 'Created' if created else 'Already exists'
        self.stdout.write(f'  {action}: PipelineStep "Unified GPT-4o"')

        self.stdout.write(self.style.SUCCESS('Bot configuration seeded successfully!'))
