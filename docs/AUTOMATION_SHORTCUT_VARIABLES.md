# Automation Shortcut Variables Helper

Copy/paste helper for building Apple Shortcuts that send Flow commands consistently.

## 1) Recommended Shortcut Variables

Define these Text variables at the top of each Shortcut:

- `FLOW_OWNER`
  - iMessage target (your own number/email used by Flow allowlist).
- `FLOW_CHANNEL`
  - One of: `text`, `calendar`, `reminder`, `note`.
- `FLOW_COMMAND`
  - Exact command from a card's `Flow Command` block.
- `FLOW_LABEL`
  - Human-readable label for this automation run.
- `FLOW_FREQUENCY`
  - For documentation inside note/log output.

Optional:

- `FLOW_WORKSPACE_ALIAS`
  - Example: `@api`, `@web-app`, `@docs`
- `FLOW_CONTEXT`
  - Extra context line injected in note-based prompts.

## 2) Normalized Payload Template

Use this for text-based execution:

```text
{{FLOW_COMMAND}}
```

Use this for note-based execution where you want metadata in the body:

```text
# {{FLOW_LABEL}} !!agent

{{FLOW_COMMAND}}

Context:
- Frequency: {{FLOW_FREQUENCY}}
- Workspace: {{FLOW_WORKSPACE_ALIAS}}
- Note: {{FLOW_CONTEXT}}
```

## 3) Channel Wrappers

### A) iMessage (`text` channel)

Actions:
1. `Text` -> value: `{{FLOW_COMMAND}}`
2. `Send Message` -> recipient: `{{FLOW_OWNER}}`

Best for:
- Immediate prompts and control commands (`health`, `status`, `usage`, `system: mute`).

### B) Calendar trigger (`calendar` channel)

Use when recurring schedule should drive execution.

Event Title Template:

```text
!!agent {{FLOW_COMMAND}}
```

Optional Event Notes Template:

```text
Automation: {{FLOW_LABEL}}
Frequency: {{FLOW_FREQUENCY}}
```

Best for:
- Recurring `plan:` prompts with structured emoji output.

### C) Reminders trigger (`reminder` channel)

Reminder Title Template:

```text
!!agent {{FLOW_COMMAND}}
```

Reminder Notes Template (optional):

```text
Automation: {{FLOW_LABEL}}
```

Best for:
- Due-date driven prompts and lightweight checks.

### D) Notes trigger (`note` channel)

Note Title Template:

```text
{{FLOW_LABEL}} !!agent
```

Note Body Template:

```text
{{FLOW_COMMAND}}

Additional context:
{{FLOW_CONTEXT}}
```

Best for:
- Long-form prompts and richer context payloads.

## 4) Prefix Guardrails

Use this decision tree when composing `FLOW_COMMAND`:

- Use `idea:` for ideation/exploration only.
- Use `plan:` by default for upkeep automations.
- Use `task:` only when you intentionally want mutation + approval.
- Use `project:` for multi-step mutation workflows with approval.
- Use plain command for built-ins (`health`, `status`, `usage today`, `system: mute`).

## 5) Required Fallback Clause

For all non-built-in prompts, append this line in command text if missing:

```text
If data unavailable, report `No signal` and list what was missing.
```

## 6) Output Contract Snippet (for recurring prompts)

Copy/paste this block into recurring prompt commands:

```text
Output sections:
🏷️ Section 1
🏷️ Section 2
🏷️ Section 3
➡️ First Action
Max length: 4-8 bullets.
```

## 7) Workspace Routing Snippet

When routing to a specific workspace alias:

```text
task: {{FLOW_WORKSPACE_ALIAS}} <instruction>
```

Examples:

```text
task: @api implement the top safe refactor candidate from today's triage
```

```text
plan: @web-app propose dependency drift mitigation steps for this week
```

## 8) Example Shortcut Configurations

### Example 1: Morning Repo Snapshot (recurring)

- `FLOW_LABEL`: `Morning Health Snapshot`
- `FLOW_CHANNEL`: `calendar`
- `FLOW_COMMAND`:

```text
plan: Produce an engineering morning snapshot for this repo.
Output sections:
🏥 Health
📊 Usage Today
⏳ Pending Approvals
🚨 Immediate Risks
➡️ First Action
Max length: 9 bullets.
If data unavailable, report `No signal` and list what was missing.
```

Event title in Calendar:

```text
!!agent {{FLOW_COMMAND}}
```

### Example 2: Inbox Triage (daily)

- `FLOW_LABEL`: `Inbox Triage Sweep`
- `FLOW_CHANNEL`: `calendar`
- `FLOW_COMMAND`:

```text
plan: Triage agent-office inbox entries into Keep, Do, Delegate, Archive candidates.
Output sections:
📥 Keep
⚙️ Do
🤝 Delegate
🗄️ Archive Candidates
➡️ First Action
Max length: 9 bullets.
If data unavailable, report `No signal` and list what was missing.
```

### Example 3: Focus Mute/Unmute Pair

Mute command:

```text
system: mute
```

Unmute command:

```text
system: unmute
```

Schedule these as two separate recurring Calendar events with `!!agent` prefix.

## 9) Sanity Checklist Before Enabling

- `FLOW_COMMAND` is copied exactly from card.
- `!!agent` exists for Calendar/Reminder/Note channels.
- Prefix choice matches intent (`plan` default for upkeep).
- Recurring prompt includes emoji output sections + max length.
- Fallback clause present.
- Avoid overlapping schedules that spam iMessage.
