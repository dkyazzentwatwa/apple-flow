# Hiring Pipeline Ops Team

## Purpose

Run recruiting funnel operations and decision readiness.

Business operations workflows across support, finance, legal, HR, and partnerships.

## Trigger Phrases

- Operational backlog spike
- SLA risk or escalation
- Leadership reporting cycle

## Inputs Required

- Process owner and business objective
- Current queue or data snapshot
- Policy/compliance constraints

## Agent Topology

- default: Orchestrates hand-offs, constraints, and final synthesis.
- explorer: Gathers context, maps unknowns, and surfaces options.
- reviewer: Evaluates risks, quality, and correctness.
- worker: Produces implementation-ready outputs.
- monitor: Tracks outcomes, regressions, and follow-ups.

## Output Contract

- Decision-oriented summary
- Prioritized actions with owners
- Operational risk flags

## Failure Modes

- Incomplete source data
- Policy ambiguity
- Cross-team dependency bottlenecks

## When to Use

- You need a structured multi-agent flow for Run recruiting funnel operations and decision readiness.
- You need explicit division between discovery, implementation, and review.
- You need a reusable operating pattern for repeated tasks in this niche.

## Anti-Pattern (Do Not Use For)

- One-line ad hoc requests where a single default agent response is sufficient.

## Approval-Sensitive Scenario

- If a mutating action affects production systems or customer-visible state, pause and route through explicit approval before execution.


