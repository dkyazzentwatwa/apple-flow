# Lead Generation Agent Team

## Purpose

Source and qualify leads for outbound prospecting, then convert that qualification into a practical outreach sequence plan.

## Trigger Phrases

- Build lead list for a specific ICP
- Define or refine ICP criteria
- Qualify new prospects by fit + intent
- Build/update outreach sequence or cadence
- Review campaign response drop or sequencing issues
- Prepare call/meeting routing for high-intent leads

## Inputs Required

- ICP definition (industry, size, geography, role, tech stack, budget, timeline)
- Outreach objective (new leads, demos, meetings, pipeline contribution)
- Channel constraints (email, LinkedIn, SMS, calls) and compliance requirements
- Available proof points (case studies, offer, pricing, success stories)

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

- Weak/dated lead data quality or missing contact-level context
- Ambiguous ICP resulting in inconsistent scoring
- Sequencing fatigue (too many/too few touches or wrong channel order)
- Over-indexing on volume without intent signals

## When to Use

- You need a structured multi-agent flow for lead generation, qualification, and outreach sequencing.
- You need explicit division between discovery, implementation, and review.
- You need a reusable operating pattern for repeated tasks in this niche.

## Anti-Pattern (Do Not Use For)

- One-line ad hoc requests where a single default agent response is sufficient.

## Approval-Sensitive Scenario

- If a mutating action affects production systems or customer-visible state, pause and route through explicit approval before execution.

