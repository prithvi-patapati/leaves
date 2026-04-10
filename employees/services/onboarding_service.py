from employees.models import OnboardingTemplate


def apply_onboarding_templates(employee):
    """Find matching templates and execute actions. Returns list of template names applied."""
    templates = OnboardingTemplate.objects.filter(is_active=True).order_by('priority')
    applied = []

    for template in templates:
        if not _matches(template, employee):
            continue
        _execute_actions(template, employee)
        applied.append(template.name)

    return applied


def _matches(template, employee):
    if template.match_department_id and template.match_department_id != employee.department_id:
        return False
    if template.match_team_id and not employee.teams.filter(pk=template.match_team_id).exists():
        return False
    if template.match_designation_id and template.match_designation_id != employee.designation_id:
        return False
    if template.match_employment_type and template.match_employment_type != employee.employment_type:
        return False
    return True


def _execute_actions(template, employee):
    """Execute template actions. Leave-crediting is handled by the leave module via signals."""
    for action in template.actions:
        action_type = action.get('type')
        if action_type == 'ADD_TO_TEAM':
            team_code = action.get('team_code')
            if team_code:
                from employees.models import Team
                try:
                    team = Team.objects.get(code=team_code, is_active=True)
                    employee.teams.add(team)
                except Team.DoesNotExist:
                    pass
        # CREDIT_LEAVES and CREATE_OVERRIDE are handled by the leave module
        # listening to the employee_created signal
