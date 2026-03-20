# Apple Flow Prompt Pack

Real prompts you can send via iMessage, Notes, Reminders, or Calendar to get work done through Apple Flow. Organized from "just got this running" to "I automate everything."

> **How it works:** In natural language mode (default), just text your message — no prefixes needed. Apple Flow figures out if it's a question, an idea, or something that changes files. For file-changing work, it asks for your approval first. You can also use explicit prefixes (`idea:`, `plan:`, `task:`, `project:`) when you want to be precise.

---

## Table of Contents

- [Level 1: First Messages](#level-1-first-messages)
- [Level 2: Daily Driver](#level-2-daily-driver)
- [Level 3: Business Owner / SMB](#level-3-business-owner--smb)
- [Level 4: Developer / Vibe Coder](#level-4-developer--vibe-coder)
- [Level 5: Power User / Automation](#level-5-power-user--automation)
- [Recurring Calendar Prompts](#recurring-calendar-prompts)
- [Reminders as a Task Queue](#reminders-as-a-task-queue)
- [Notes for Long-Form Work](#notes-for-long-form-work)
- [Agent Office Workflows](#agent-office-workflows)
- [Control Commands Reference](#control-commands-reference)

---

## Level 1: First Messages

You just set up Apple Flow. Here's what to text to make sure it's alive and learn what it can do.

### Check that it works

```
health
```

Returns uptime, message count, session count. If you get a reply, you're live.

### Ask a simple question

```
What's the difference between an LLC and an S-Corp?
```

No prefix needed. Just ask like you're texting a friend who knows everything.

### Get an idea

```
idea: I want to start a newsletter but I don't know what to write about
```

Returns brainstormed options, trade-offs, and a recommendation.

### Ask for a plan

```
plan: Launch a landing page for my consulting business
```

Returns a step-by-step plan with acceptance criteria. Nothing gets changed — it's just a plan.

### See your history

```
history
```

Shows your recent messages. Or search for something specific:

```
history: landing page
```

### Start fresh

```
clear context
```

Wipes the conversation context so you start from a clean slate.

---

## Level 2: Daily Driver

You're comfortable. You text Apple Flow a few times a day.

### Research and summarize

```
What are the top 3 project management tools for a 5-person team? Compare pricing.
```

```
Summarize the pros and cons of Shopify vs WooCommerce for a small retail store
```

```
What tax deductions can a sole proprietor claim for a home office?
```

### Brainstorm with context

```
idea: My bakery wants to do catering but we've never done it before. What would a minimum viable catering offer look like?
```

```
idea: I need a 30-day social media content calendar for a local gym
```

```
idea: Ways to reduce customer churn for a monthly subscription box
```

### Plan real work

```
plan: Migrate our team from Slack to Microsoft Teams without losing anything
```

```
plan: Set up a basic inventory tracking system for our warehouse using spreadsheets
```

```
plan: Create an onboarding checklist for new hires at a 10-person company
```

### Execute tasks (requires approval)

```
task: Write a professional email template for following up with leads who went cold
```

```
task: Create a CSV template for tracking monthly expenses with categories
```

```
task: Draft a return policy for our e-commerce store
```

When you send a `task:`, Apple Flow will show you a preview and ask for approval. Reply `approve <id>` to proceed or `deny <id>` to cancel.

### Check pending approvals

```
status
```

Shows all pending approvals with their IDs. Then:

```
approve abc123
```

```
deny abc123
```

```
deny all
```

---

## Level 3: Business Owner / SMB

You run a business. Apple Flow is your always-on assistant.

### Operations

```
plan: Create a standard operating procedure for handling customer complaints
```

```
task: Draft an employee handbook section covering PTO policy, sick days, and remote work
```

```
idea: We're getting 50 orders/day and fulfillment is breaking. What should we automate first?
```

```
Write a checklist for opening and closing procedures at a retail store
```

### Marketing and sales

```
task: Write 5 Google Ads headlines and descriptions for a local plumbing company
```

```
plan: Launch an email drip campaign for new customers — 5 emails over 30 days
```

```
idea: We have 2,000 email subscribers but only 15% open rate. How do we fix this?
```

```
task: Draft a case study template I can fill in for each client project
```

### Finance and admin

```
plan: Set up a monthly financial review process for a small business
```

```
What's the difference between cash basis and accrual accounting? Which is better for a business doing $500K/year?
```

```
task: Create a simple profit & loss statement template in markdown
```

### Hiring

```
task: Write a job posting for a part-time social media manager
```

```
plan: Design a 3-round interview process for a senior developer role
```

```
idea: Should we hire a full-time accountant or keep using our bookkeeper and CPA?
```

### Client work

```
task: Draft a project proposal template with scope, timeline, pricing, and terms sections
```

```
task: Write a polite but firm email for a client who's 30 days past due on an invoice
```

```
plan: Create a client offboarding process — handoff, final deliverables, feedback survey
```

---

## Level 4: Developer / Vibe Coder

You write code. Apple Flow runs tasks in your workspace.

### Quick questions from your phone

```
How do I set up a GitHub Actions workflow that runs tests on every PR?
```

```
What's the best way to handle authentication in a Next.js app?
```

```
Explain the difference between optimistic and pessimistic locking in databases
```

### Code tasks (with workspace routing)

If you have multiple workspaces configured with `@alias`:

```
task: @web-app Add a 404 page that matches our design system
```

```
task: @api Add rate limiting middleware to all public endpoints
```

```
task: @docs Update the API reference for the new /users endpoint
```

Without aliases (uses your default workspace):

```
task: Add input validation to the signup form — email format, password minimum 8 chars
```

```
task: Write unit tests for the calculateTotal function in utils.py
```

```
task: Fix the bug where the navbar disappears on mobile when scrolling up
```

### Planning and architecture

```
plan: Refactor the monolithic Express app into a modular structure with separate route files
```

```
plan: Add Stripe payment integration — subscription model with free trial
```

```
idea: We're hitting rate limits on our third-party API. What caching strategies make sense?
```

```
plan: Migrate from REST to GraphQL for the mobile app's data layer
```

### Project-level work

```
project: @web-app Build a user dashboard with usage stats, recent activity, and account settings
```

```
project: Set up a CI/CD pipeline — lint, test, build, deploy to staging on PR merge
```

### Debugging from anywhere

```
The deploy failed with "module not found: @/lib/auth". What's likely wrong and how do I fix it?
```

```
Our API is returning 502 errors intermittently. What should I check first?
```

```
history: deploy
```

### Monitor usage and costs

```
usage
```

```
usage today
```

```
usage monthly
```

```
usage blocks
```

---

## Level 5: Power User / Automation

You've been using Apple Flow for a while. Time to automate.

### Companion controls

Mute proactive messages when you need focus time:

```
system: mute
```

Turn them back on:

```
system: unmute
```

### Workspace-aware batch work

```
task: @web-app Update all API calls to use the new v2 endpoints
```

Then immediately queue the next:

```
task: @api Deprecate v1 endpoints with a 30-day sunset header
```

### Context-aware follow-ups

Apple Flow remembers your recent conversation. Use that:

```
Actually, also add error handling for network timeouts in that same file
```

```
Can you revise that plan to include a rollback strategy?
```

```
Take that email template and make a version for enterprise clients too
```

### Multi-channel orchestration

Send a detailed spec via **Apple Notes** (folder: `agent-task`):

```
# Refactor Auth Module

Current auth uses session cookies. Migrate to JWT with refresh tokens.

Requirements:
- Access token: 15 min expiry
- Refresh token: 7 day expiry
- Store refresh tokens in httpOnly cookies
- Add /auth/refresh endpoint
- Update all middleware to validate JWT
- Keep backward compat for 2 weeks

Workspace: @api
```

Then monitor via **iMessage**:

```
status
```

### System administration

View daemon logs:

```
logs
```

```
logs 50
```

Check health:

```
health
```

Remote shutdown:

```
system: stop
```

Remote restart:

```
system: restart
```

---

## Recurring Calendar Prompts

Create these as **recurring events** in your Apple Calendar (in the calendar configured for Apple Flow, default: `agent-schedule`). The event title is the prompt. When the event comes due (within the lookahead window), Apple Flow picks it up and executes it.

> **Trigger tag required:** By default, events must include `!!agent` somewhere in the title or description to be picked up. This prevents random calendar events from becoming tasks. The tag is stripped before processing. You can change or disable this via `apple_flow_trigger_tag` in your `.env`.

### Daily recurring

| Event Title | Recurrence | Time | Purpose |
|---|---|---|---|
| `!!agent What's on my calendar today and what should I prioritize?` | Every weekday | 7:30 AM | Morning prioritization |
| `!!agent idea: Give me one actionable marketing idea I can execute today` | Every weekday | 8:00 AM | Daily marketing nudge |
| `!!agent health` | Every day | 9:00 AM | Confirm daemon is running |
| `!!agent status` | Every day | 12:00 PM | Midday approval check |
| `!!agent Summarize what I accomplished today based on my recent message history` | Every weekday | 5:30 PM | End-of-day recap |

### Weekly recurring

| Event Title | Recurrence | Day/Time | Purpose |
|---|---|---|---|
| `!!agent plan: Review this week's goals and create next week's top 3 priorities` | Weekly | Monday 8:00 AM | Weekly planning |
| `!!agent idea: What's one process in my business I should automate this week?` | Weekly | Monday 9:00 AM | Automation brainstorm |
| `!!agent task: Draft a weekly team update email summarizing progress and blockers` | Weekly | Friday 3:00 PM | Team comms |
| `!!agent usage monthly` | Weekly | Friday 4:00 PM | Cost tracking |
| `!!agent idea: Based on my recent history, what patterns do you see in what I'm working on? Am I focused or scattered?` | Weekly | Sunday 7:00 PM | Self-reflection |

### Monthly recurring

| Event Title | Recurrence | Day/Time | Purpose |
|---|---|---|---|
| `!!agent plan: Monthly business review — what metrics should I look at and what questions should I ask?` | 1st of month | 9:00 AM | Monthly review prep |
| `!!agent task: Create a checklist of recurring monthly tasks — renewals, payments, reports` | 1st of month | 10:00 AM | Admin catch-all |
| `!!agent idea: What should I learn or improve this month to grow the business?` | 1st of month | 8:00 AM | Growth planning |
| `!!agent plan: Review and update our project roadmap for the coming month` | Last weekday of month | 2:00 PM | Roadmap hygiene |

### Quarterly recurring

| Event Title | Recurrence | Quarterly | Purpose |
|---|---|---|---|
| `!!agent plan: Quarterly business review — revenue trends, customer growth, top wins, biggest problems` | 1st of quarter | 9:00 AM | QBR prep |
| `!!agent idea: If I could only work on one thing next quarter, what would move the needle most?` | 1st of quarter | 10:00 AM | Strategic focus |
| `!!agent task: Draft a quarterly investor/stakeholder update email` | End of quarter | 3:00 PM | Stakeholder comms |

---

## Reminders as a Task Queue

Add items to your Apple Reminders list (default: `agent-task`) and Apple Flow picks them up. Great for capturing tasks on the go.

> **Trigger tag required:** Include `!!agent` in the reminder name or notes. This tells Apple Flow to pick it up. The tag is stripped before processing.

### Quick captures from your phone

- `!!agent Write a thank-you email to the client from today's meeting`
- `!!agent Research competitors' pricing for our premium tier`
- `!!agent Draft social media copy for the product launch next Tuesday`
- `!!agent Add error logging to the payment processing module`
- `!!agent Create a packing list template for our shipping team`

### With due dates

Set a due date on the reminder and Apple Flow processes it when it's due:

- `!!agent Prepare agenda for Monday's team standup` — due Monday 8:00 AM
- `!!agent Send invoice to Client X for January work` — due Feb 1
- `!!agent Review and rotate API keys` — due 1st of every month
- `!!agent Check SSL certificate expiry dates` — due quarterly

### Siri integration

Since these are just Apple Reminders, use Siri:

> "Hey Siri, add a reminder to my agent-task list: bang bang agent Write a blog post about our new feature"

> "Hey Siri, remind me in agent-task tomorrow at 9 AM to bang bang agent review the pull requests"

(Siri interprets "bang bang agent" as `!!agent` — or just add the tag manually after Siri creates the reminder.)

---

## Notes for Long-Form Work

For tasks that need more context than a text message, create a note in your Apple Notes folder (default: `agent-task`). Apple Flow reads the full note body as the prompt.

> **Trigger tag required:** Include `!!agent` somewhere in the note title or body. The tag is stripped before processing.

### Detailed spec

```
# Email Drip Campaign !!agent

Create a 5-email welcome sequence for new subscribers.

Audience: Small business owners who signed up for our free project management tool.

Email 1 (Day 0): Welcome + quick win (how to create first project)
Email 2 (Day 2): Feature highlight (team collaboration)
Email 3 (Day 5): Case study (how XYZ Co saved 10 hrs/week)
Email 4 (Day 8): Pro tip (integrations and automations)
Email 5 (Day 12): Upgrade pitch (premium features, limited-time offer)

Tone: Friendly, helpful, not salesy. Like a knowledgeable friend.
Length: 150-200 words each.
Include subject lines with A/B variants.
```

### Code review request

```
# Review Auth Implementation !!agent

Review the authentication module at @api workspace.

Check for:
- OWASP top 10 vulnerabilities
- Token expiry and refresh logic
- Rate limiting on login attempts
- Password hashing algorithm (should be bcrypt or argon2)
- Session invalidation on password change

Return findings as a prioritized list: critical, warning, suggestion.
```

### Research brief

```
# Competitor Analysis !!agent

Research these competitors:
- Asana
- Monday.com
- ClickUp
- Notion

For each, find:
1. Pricing tiers and per-seat cost
2. Key differentiating features
3. What users complain about most (check Reddit, G2)
4. Recent major feature launches (last 6 months)

Format as a comparison table, then a 3-paragraph summary of where gaps exist that we could exploit.
```

### Process documentation

```
# Document Our Deployment Process !!agent

Interview the codebase at @api and create deployment documentation.

Include:
- Prerequisites (environment, credentials, access)
- Step-by-step deployment to staging
- Step-by-step deployment to production
- Rollback procedure
- Post-deploy verification checklist
- Common failure modes and fixes

Write it so a new developer could deploy on their first day.
```

---

## Agent Office Workflows

The agent-office scaffold (`agent-office/`) is a structured workspace the companion uses for durable memory and notes. Here's how to leverage it.

### Understanding the structure

```
agent-office/
  SOUL.md              # Companion personality — edit this to change how it talks
  MEMORY.md            # Persistent memory — injected into every prompt
  00_inbox/inbox.md    # Quick capture — companion checks for untriaged items
  10_daily/            # Daily digest notes (auto-generated if enabled)
  20_projects/         # Project briefs you create
  60_memory/           # Topic-specific memory files (auto-generated by ambient scanner)
  80_automation/       # Playbooks and routines
  90_logs/             # Companion activity log
```

### Seed your memory

Edit `agent-office/MEMORY.md` to give the companion context it should always have:

```markdown
# Memory

## About me
- I run a SaaS company called Acme Tools (B2B project management)
- 12-person team, Series A, based in Austin
- I'm the CEO and still write code sometimes

## Current priorities
- Launch v2.0 by March 15
- Hire a senior frontend developer
- Reduce churn from 8% to 5%

## Preferences
- I prefer concise answers — bullet points over paragraphs
- My code stack: Next.js, Python/FastAPI, PostgreSQL, Vercel
- I check messages between 7 AM and 10 PM Central
```

### Use the inbox for quick captures

Add items to `agent-office/00_inbox/inbox.md`:

```markdown
## Entries
- [ ] 2025-02-20 14:30 | idea | What if we added a Slack integration?
- [ ] 2025-02-20 15:00 | task | Update pricing page with new Enterprise tier
- [ ] 2025-02-20 16:00 | followup | Check if Client Y responded to proposal
```

The companion picks these up during its observation loop and can act on them.

### Create project briefs

Add markdown files to `agent-office/20_projects/`:

```markdown
# V2 Launch

## Goal
Ship v2.0 with new dashboard, team permissions, and Stripe billing.

## Status
In progress — dashboard 80% done, permissions 50%, billing not started.

## Key decisions
- Using Stripe Checkout (not custom billing UI)
- Role-based permissions: admin, editor, viewer
- Dashboard built with Recharts

## Blockers
- Need design review on permissions UI
- Stripe webhook testing environment not set up
```

### Customize the companion personality

Edit `agent-office/SOUL.md` to change how the companion communicates. The default is concise and professional. You might want:

- **More casual:** Add "Use informal language. It's okay to be funny."
- **More detailed:** Add "Default to thorough explanations unless asked to be brief."
- **Domain-specific:** Add "You're assisting a medical practice. Be precise with terminology."
- **Bilingual:** Add "Respond in Spanish when I message in Spanish."

---

## Control Commands Reference

Quick reference for system commands. Send these as plain iMessages.

| Command | What it does |
|---|---|
| `health` | Daemon status, uptime, message count |
| `status` | List pending approvals |
| `approve <id>` | Approve a pending task |
| `deny <id>` | Deny a pending task |
| `deny all` | Cancel all pending approvals |
| `history` | Recent message history |
| `history: <query>` | Search message history |
| `usage` | Token usage (last 7 days) |
| `usage today` | Today's token usage |
| `usage monthly` | Monthly token usage |
| `usage blocks` | Billing block breakdown |
| `logs` | Last 20 lines of daemon log |
| `logs 50` | Last 50 lines of daemon log |
| `clear context` | Reset conversation context |
| `system: mute` | Silence companion proactive messages |
| `system: unmute` | Re-enable companion messages |
| `system: stop` | Shut down Apple Flow |
| `system: restart` | Restart Apple Flow |
| `system: sync` | Sync agent-office to cloud backup |

---

## Tips

- **No prefix needed.** In natural language mode, just type what you want. Apple Flow auto-detects if it needs to create/modify files and routes through the approval flow.
- **Approval is your safety net.** Anything that changes files requires your explicit `approve`. You're always in control.
- **Use `idea:` for thinking, `plan:` for planning, `task:` for doing.** The prefixes aren't required but they set the right mode — brainstorm, structured plan, or execute.
- **Calendar events repeat.** Set up recurring calendar events in your agent calendar for prompts you want to run on a schedule. This is the killer feature for hands-off automation.
- **Siri works.** "Hey Siri, add a reminder to agent-task: ..." captures tasks without opening your phone.
- **Notes for big prompts.** If your prompt is longer than a text message, put it in an Apple Note instead.
- **Memory compounds.** The more you use Apple Flow, the better it gets. The ambient scanner builds topic memory, the companion learns your patterns, and conversation history adds context.
- **Mute when you need focus.** `system: mute` stops proactive messages. `system: unmute` brings them back.
