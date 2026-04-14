from django.core.management.base import BaseCommand
from bot.models import Bot, LLMProvider, Pipeline, PipelineStep, Prompt


# ── System Prompts (per role) ──

EMPLOYEE_PROMPT = """You are Gamyam's leave assistant for {name} ({emp_id}).
Department: {dept} | Role: {designation} | Manager: {manager}
Today: {today} | Leave year: {leave_year} (Apr {leave_year} – Mar {next_year})

RULES:
- ONLY discuss leave management.
- NEVER fabricate data. Only state facts from tool results.
- Use leave type CODES: SL, PL, EL, LOP, WFH, BL, ML, PtL, OH.
- Generate idempotency_key as: {emp_id}_action_{today}_XXXX."""

MANAGER_PROMPT = """You are Gamyam's leave assistant for {name} ({emp_id}), a manager.
Department: {dept} | Role: {designation}
Today: {today} | Leave year: {leave_year}

RULES:
- ONLY discuss leave management.
- NEVER fabricate data. Only state facts from tool results.
- Use the 'id' field from get_team_requests as request_id for approve/reject. NEVER guess IDs.
- Generate idempotency_key as: MGR_{emp_id}_action_{today}_XXXX."""

ADMIN_PROMPT = """You are Gamyam's HRMS assistant for {name} ({emp_id}), an HR administrator.
Today: {today} | Leave year: {leave_year}
You have FULL access to all 48 tools.

RULES:
- ONLY discuss HRMS operations.
- NEVER fabricate data. Only state facts from tool results.
- If results are empty, say so clearly.
- Confirm before destructive actions.
- Generate idempotency_key as: HR_{emp_id}_action_{today}_XXXX."""


# ── Pipeline Step Prompts ──

INTENT_CLASSIFY_PROMPT = """Classify this message into exactly ONE intent. Return ONLY the intent word.

Intents:
BALANCE_CHECK — checking leave balance
APPLY_LEAVE — applying or requesting leave
CANCEL_LEAVE — cancelling a leave request
POLICY_QUERY — asking about leave policies or rules
VIEW_REQUESTS — viewing leave requests
APPROVE_REJECT — approving or rejecting requests
TEAM_OVERVIEW — team calendar, team balance, who's off
EMPLOYEE_LOOKUP — searching or viewing employee details
EMPLOYEE_MGMT — adding, updating, transferring, deactivating employees
DEPT_TEAM — department or team queries
POLICY_CHANGE — creating, updating, deactivating leave types
OVERRIDE — creating or removing employee overrides
BALANCE_ADJUST — crediting or deducting leave days
SYSTEM_OP — bulk credit, monthly accrual, year-end processing
HR_ACTIONS — HR action queue
HOLIDAY — optional holidays
GREETING — greetings, thanks, bye
OTHER — not HR related

User ({role}): "{user_message}"
Intent:"""

TOOL_PLAN_PROMPT = """Plan which tools to call. Return a JSON array: [{{"tool": "name", "args": {{...}}}}]

Rules:
- APPLY_LEAVE: plan get_my_balance then validate_leave. Do NOT plan apply_leave.
- CANCEL_LEAVE: plan get_my_requests first.
- APPROVE_REJECT: plan get_team_requests first. NEVER guess IDs.
- POLICY_CHANGE: plan get_leave_policy first.
- OVERRIDE: plan get_overrides first.
- SYSTEM_OP (year_end): plan with dry_run=true.
- BALANCE_ADJUST: plan get_employee first.
- Use leave type CODES: SL, PL, EL, LOP, WFH, BL, ML, PtL, OH.
- Dates in YYYY-MM-DD. Today is {today}.

Available tools: {tool_names}
Intent: {intent}
User ({role}): "{user_message}"

JSON plan:"""

RESPONSE_GEN_PROMPT = """Write a clear, concise response based on the tool results.

Rules:
- ONLY state facts from tool results. NEVER make up data.
- If results are empty, say so plainly.
- Be concise: 2-3 sentences for simple queries, bullet points for lists.
- Use the employee's first name.
- Do NOT describe buttons or UI — they are added automatically.
- Do NOT say "let me check" — the data is already here.
{previous_output}
Employee: {name} ({role})
User asked: "{user_message}"
Tool results:
{tool_results}

Response:"""

REVIEW_PROMPT = """Review this HR assistant response. Check:
1. Does it answer the user's question?
2. Does it contain ANY data not in the tool results? (hallucination)
3. Is anything important missing?
4. Is it concise?

Tool results:
{tool_results}

User question: "{user_message}"
Response: "{previous_output}"

If good, return: APPROVED
If needs fixing, return: REDO: <what to fix>"""

TOOL_FIX_PROMPT = """Tool "{tool_name}" failed: {error}
Original args: {tool_results}
Fix the arguments. Return ONLY corrected JSON args object."""


class Command(BaseCommand):
    help = 'Seed bot configuration with smart pipeline'

    def handle(self, *args, **options):
        # LLM Providers
        gpt4o, c = LLMProvider.objects.get_or_create(
            model_id='gpt-4o',
            defaults={'name': 'GPT-4o', 'provider_type': 'openai', 'is_active': True,
                      'description': 'OpenAI GPT-4o'})
        self.stdout.write(f"  {'Created' if c else 'Exists'}: GPT-4o")

        LLMProvider.objects.get_or_create(
            model_id='xlam',
            defaults={'name': 'xLAM-2-1B', 'provider_type': 'local', 'is_active': False,
                      'api_url': 'http://host.docker.internal:8081/v1'})
        LLMProvider.objects.get_or_create(
            model_id='gemma',
            defaults={'name': 'Gemma-3-1B', 'provider_type': 'local', 'is_active': False,
                      'api_url': 'http://host.docker.internal:8082/v1'})

        # Prompts
        prompts = {}
        for name, template in [
            ('Employee System Prompt', EMPLOYEE_PROMPT),
            ('Manager System Prompt', MANAGER_PROMPT),
            ('Admin System Prompt', ADMIN_PROMPT),
            ('Intent Classifier', INTENT_CLASSIFY_PROMPT),
            ('Tool Planner', TOOL_PLAN_PROMPT),
            ('Response Generator', RESPONSE_GEN_PROMPT),
            ('Response Reviewer', REVIEW_PROMPT),
            ('Tool Error Fixer', TOOL_FIX_PROMPT),
        ]:
            p, c = Prompt.objects.get_or_create(
                name=name, defaults={'template': template, 'is_active': True})
            prompts[name] = p
            self.stdout.write(f"  {'Created' if c else 'Exists'}: Prompt '{name}'")

        # Pipeline
        pipeline, c = Pipeline.objects.get_or_create(
            name='Smart Pipeline',
            defaults={'is_active': True,
                      'description': 'Intent classification → simple (fast) or complex (thorough) path.'})
        self.stdout.write(f"  {'Created' if c else 'Exists'}: Pipeline")

        # Clear existing steps for this pipeline (so re-running updates them)
        if not c:
            PipelineStep.objects.filter(pipeline=pipeline).delete()

        # System prompts (per role)
        PipelineStep.objects.create(
            pipeline=pipeline, order=0, name='Employee System Prompt',
            step_type='system_prompt', prompt=prompts['Employee System Prompt'],
            role_filter='EMPLOYEE', is_active=True)
        PipelineStep.objects.create(
            pipeline=pipeline, order=1, name='Manager System Prompt',
            step_type='system_prompt', prompt=prompts['Manager System Prompt'],
            role_filter='MANAGER', is_active=True)
        PipelineStep.objects.create(
            pipeline=pipeline, order=2, name='Admin System Prompt',
            step_type='system_prompt', prompt=prompts['Admin System Prompt'],
            role_filter='ADMIN', is_active=True)

        # Intent classification
        PipelineStep.objects.create(
            pipeline=pipeline, order=10, name='Intent Classifier',
            step_type='classify', llm_provider=gpt4o,
            prompt=prompts['Intent Classifier'], is_active=True,
            config={
                'simple_intents': [
                    'BALANCE_CHECK', 'POLICY_QUERY', 'VIEW_REQUESTS', 'TEAM_OVERVIEW',
                    'EMPLOYEE_LOOKUP', 'DEPT_TEAM', 'GREETING', 'HOLIDAY', 'HR_ACTIONS', 'OTHER',
                ],
                'complex_intents': [
                    'APPLY_LEAVE', 'CANCEL_LEAVE', 'APPROVE_REJECT', 'EMPLOYEE_MGMT',
                    'POLICY_CHANGE', 'OVERRIDE', 'BALANCE_ADJUST', 'SYSTEM_OP',
                ],
                'max_tokens': 20,
                'temperature': 0,
            })

        # Simple path: all-in-one tool call + reply
        PipelineStep.objects.create(
            pipeline=pipeline, order=20, name='Simple: Tool Call + Reply',
            step_type='reply', llm_provider=gpt4o, is_active=True,
            config={'max_rounds': 10, 'tool_choice': 'auto', 'for_path': 'simple'})

        # Complex path: tool planning
        PipelineStep.objects.create(
            pipeline=pipeline, order=30, name='Complex: Tool Planner',
            step_type='plan', llm_provider=gpt4o,
            prompt=prompts['Tool Planner'], is_active=True,
            config={'max_tokens': 500, 'temperature': 0, 'for_path': 'complex'})

        # Complex path: tool execution with retry
        PipelineStep.objects.create(
            pipeline=pipeline, order=40, name='Complex: Tool Execution',
            step_type='tool_call', llm_provider=gpt4o, is_active=True,
            prompt=prompts['Tool Error Fixer'],
            config={'retry_on_error': True, 'max_retries': 3, 'for_path': 'complex'})

        # Complex path: response generation
        PipelineStep.objects.create(
            pipeline=pipeline, order=50, name='Complex: Response Generator',
            step_type='generate', llm_provider=gpt4o,
            prompt=prompts['Response Generator'], is_active=True,
            config={'max_tokens': 500, 'for_path': 'complex'})

        # Complex path: review & validate
        PipelineStep.objects.create(
            pipeline=pipeline, order=60, name='Complex: Response Reviewer',
            step_type='validate', llm_provider=gpt4o,
            prompt=prompts['Response Reviewer'], is_active=True,
            config={'max_retries': 1, 'temperature': 0, 'for_path': 'complex'})

        self.stdout.write(f"  Created: 9 Pipeline Steps")

        # Bot
        Bot.objects.update_or_create(
            name='HRMS Slack Bot',
            defaults={'connector_type': 'slack', 'status': 'active', 'pipeline': pipeline,
                      'description': 'Main HRMS leave management Slack bot'})
        self.stdout.write(f"  Created/Updated: Bot")

        self.stdout.write(self.style.SUCCESS('Smart pipeline seeded!'))
