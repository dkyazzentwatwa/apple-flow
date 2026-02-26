# Companion Proactive Coach

## Purpose

Drive proactive nudges and assistant follow-up quality.

Apple Flow operations on macOS gateways (iMessage, Mail, Reminders, Notes, Calendar).

## Trigger Phrases

- "task:"
- "project:"
- "status"
- "approve <id>"

## Inputs Required

- Gateway context (message/email/reminder/note/event)
- Current objective and constraints
- Approval requirements and timeline

## Agent Topology

- default: Orchestrates hand-offs, constraints, and final synthesis.
- explorer: Gathers context, maps unknowns, and surfaces options.
- reviewer: Evaluates risks, quality, and correctness.
- worker: Produces implementation-ready outputs.
- monitor: Tracks outcomes, regressions, and follow-ups.

## Output Contract

- Action plan with gateway routing
- Execution log or proposed approval-safe action
- Follow-up checklist and owner

## Failure Modes

- Missing sender allowlist context
- Approval deadlock or expiry
- Ambiguous gateway source record

## When to Use

- You need a structured multi-agent flow for Drive proactive nudges and assistant follow-up quality.
- You need explicit division between discovery, implementation, and review.
- You need a reusable operating pattern for repeated tasks in this niche.

## Anti-Pattern (Do Not Use For)

- One-line ad hoc requests where a single default agent response is sufficient.

## Approval-Sensitive Scenario

- If a mutating action affects production systems or customer-visible state, pause and route through explicit approval before execution.

## Apple Flow Usage Examples

- task: review unread reminders and close stale items
- project: triage todays notes and produce action queue
- plan: map cross-gateway handoff for weekly operations

