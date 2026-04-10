# Gamyam HRMS — Leave Management System

A config-driven, agent-ready leave management system built with Django. HR manages policies and employee exceptions through a Slack chatbot or REST API. Managers approve requests through Slack or a web interface.

## Quick Start (Local Development)

### Prerequisites
- Python 3.12+
- pip

### Setup

```bash
git clone <repo>
cd leaves
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Load org data (66 employees from xlsx)
python manage.py migrate
python manage.py seed_departments
python manage.py seed_designations
python manage.py import_employees
python manage.py seed_company_config
python manage.py seed_leave_types
python manage.py bulk_credit_leaves --year 2026
python manage.py seed_onboarding_templates

# Start server
python manage.py runserver
```

Open http://localhost:8000/approve/ for the manager approval screen.

---

## Quick Start (Docker)

### Prerequisites
- Docker & Docker Compose

### Setup

```bash
# Create .env file with your tokens
cp .env.example .env
# Edit .env — fill in SLACK_BOT_TOKEN, SLACK_APP_TOKEN, OPENAI_API_KEY

# Start everything
docker-compose up --build

# First boot: ~2 min (postgres init + migrations + data seed)
# You'll see: "=== HRMS API ready on :8000 ==="
```

Services:
- **API:** http://localhost:8000
- **Manager Approvals:** http://localhost:8000/approve/
- **PostgreSQL:** localhost:5432
- **Redis:** localhost:6379

---

## Slack Setup

### 1. Create Slack App

Go to https://api.slack.com/apps -> Create New App -> From scratch

**App Name:** Gamyam HRMS
**Workspace:** Your workspace

### 2. Enable Socket Mode

- Left sidebar -> Socket Mode -> Enable
- Create App-Level Token: name it `hrms-socket`, scope `connections:write`
- Copy the token -> `SLACK_APP_TOKEN` (starts with `xapp-`)

### 3. Add Bot Permissions

Left sidebar -> OAuth & Permissions -> Bot Token Scopes:
- `app_mentions:read`
- `chat:write`
- `commands`
- `im:history`
- `im:read`
- `im:write`

### 4. Create Slash Commands

Left sidebar -> Slash Commands -> Create:

| Command | Description | Usage Hint |
|---|---|---|
| `/employee` | Login as employee | GIT-001 |
| `/hr` | Login as HR admin | |
| `/manager` | Login as manager | GIT-023 |
| `/whoami` | Show current role | |
| `/reset` | Clear conversation | |

### 5. Enable Events

Left sidebar -> Event Subscriptions -> Enable -> Subscribe to bot events:
- `message.im`
- `app_mention`

### 6. Install App

Left sidebar -> Install App -> Install to Workspace -> Copy Bot Token -> `SLACK_BOT_TOKEN` (starts with `xoxb-`)

### 7. Add Tokens to .env

```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
OPENAI_API_KEY=sk-...
```

### 8. Restart

```bash
docker-compose restart slack
```

---

## Using the System

### As Employee (Slack)

```
/employee GIT-001
What's my leave balance?
I want 2 days sick leave from yesterday
Cancel my last leave request
```

### As Manager (Slack)

```
/manager GIT-023
Show pending requests
Approve Prithvi's request
```

### As Manager (Web)

Open http://localhost:8000/approve/
Select a manager from the dropdown.
Click Approve or Reject on pending cards.

### As HR Admin (Slack)

```
/hr
Block WFH for Akshay for May. He's on probation.
Increase sick leave to 10 days. Retroactive.
Add new employee: Raj, GIT-077, raj@gamyam.co, male, Engineering, Software Developer, reports to Chandrakala
```

---

## Employee IDs for Testing

| ID | Name | Role | Notes |
|---|---|---|---|
| GIT-001 | Prithvi Patapati | Sr. Software Engineer | Reports to Chandrakala |
| GIT-002 | Meena Rangari | Sr. Software Engineer | Reports to Chandrakala |
| GIT-017 | Saiteja VMVN | CEO | Top of chain |
| GIT-023 | Chandrakala Tirumalla | Sr. Project Manager | 47 reports |
| GIT-008 | Dinesh Gonti | Sr. Program Manager | Fallback manager |
| GIT-046 | Bhavishya Reddy | Sr. HR Manager | HR admin |
| GIT-053 | Akshay Sharma | Software Developer | On probation |

---

## Architecture

```
Slack (user) -> Slack Connector (OpenAI + tools) -> Django API -> PostgreSQL
Browser (HR) -> Approve page -> Django API -> PostgreSQL
```

The system has 4 components:
- **Config** — default policy rules for everyone
- **Override** — per-employee exceptions
- **Engine** — reads config + overrides, executes
- **Actions** — human-triggered operations

48 MCP tools across 3 roles (Employee: 8, Manager: 6, Admin: 34).

---

## Management Commands

```bash
python manage.py seed_departments              # Create departments
python manage.py seed_designations             # Create designations
python manage.py import_employees              # Import 66 employees from xlsx
python manage.py seed_company_config           # Company settings
python manage.py seed_leave_types              # Seed 9 leave types
python manage.py bulk_credit_leaves --year 2026  # Credit balances
python manage.py seed_onboarding_templates     # Default onboarding
```

---

## Running Tests

```bash
source venv/bin/activate
python manage.py test tests/ -v2   # 263 tests
```

---

## License

Internal use only — Gamyam Info Tech LLP
