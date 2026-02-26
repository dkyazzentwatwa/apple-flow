# Engagement and Nurturing Team

## Purpose

Track engagement and orchestrate effective nurture sequences.

Software delivery and go-to-market coordination workflows.

## Trigger Phrases

- New feature request
- Regression report
- Pipeline or campaign drop

## Inputs Required

- Product or campaign goals
- Constraints (time, budget, compliance)
- Existing metrics or code context

## Agent Topology

- default: Orchestrates hand-offs, constraints, and final synthesis.
- explorer: Gathers context, maps unknowns, and surfaces options.
- reviewer: Evaluates risks, quality, and correctness.
- worker: Produces implementation-ready outputs.
- monitor: Tracks outcomes, regressions, and follow-ups.

## Output Contract

- Prioritized execution plan
- Risk/quality findings
- Measurable next actions

## Failure Modes

- Missing baseline metrics
- Contradictory stakeholder requirements
- Scope creep beyond objective

## When to Use

- You need a structured multi-agent flow for Track engagement and orchestrate effective nurture sequences.
- You need explicit division between discovery, implementation, and review.
- You need a reusable operating pattern for repeated tasks in this niche.

## Anti-Pattern (Do Not Use For)

- One-line ad hoc requests where a single default agent response is sufficient.

## Approval-Sensitive Scenario

- If a mutating action affects production systems or customer-visible state, pause and route through explicit approval before execution.


