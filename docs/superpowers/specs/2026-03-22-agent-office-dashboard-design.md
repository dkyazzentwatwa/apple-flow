# Agent-Office Web Dashboard Design

**Date:** 2026-03-22

## Goal

Add a lightweight mobile-friendly web dashboard for `agent-office` that is served by the existing Apple Flow admin service and accessible over Tailscale from a phone.

## Summary

The dashboard should feel like a mixed command center:

- a top status strip for daemon and companion health
- filesystem-oriented summaries for key `agent-office` folders
- a few safe controls such as `mute/unmute` and refresh

This should not introduce a second long-running service. The dashboard should be read-heavy, low-risk, and reuse existing admin API authentication.

## Why This Approach

The repo already has:

- a 24/7 Python daemon
- a FastAPI admin service
- structured `agent-office` conventions
- companion and approval state already stored in SQLite

Serving the dashboard from the existing FastAPI app keeps deployment simple, avoids extra process management, and fits phone access over Tailscale well.

## User Experience

### Home Screen

The landing page should show:

- daemon health
- companion muted/unmuted state
- last companion check time
- last companion send time
- pending approvals count
- last refresh timestamp

Below the top status strip, the page should show cards for:

- `00_inbox`
- `10_daily`
- `60_memory`
- `30_outputs`
- `40_resources`
- `90_logs`

Each card should include:

- item count or summary count
- last modified time
- short preview text when safe and useful
- a tap target that opens a more detailed section view

### Section Detail Views

Each major area should have a simple detail page or panel with:

- recent files
- sizes
- last modified times
- preview snippets for Markdown/text files

The dashboard should be optimized for narrow/mobile screens first.

## Safe Actions In V1

Allowed actions:

- refresh dashboard data
- mute companion
- unmute companion
- quick links or buttons for inbox, today, and memory summaries

Excluded from v1:

- arbitrary file editing
- destructive file operations
- arbitrary filesystem browsing
- approval mutation actions
- rich collaborative editing

## Architecture

### Server Placement

The existing admin FastAPI app in `src/apple_flow/main.py` should serve:

- one HTML dashboard route
- one small static asset surface if needed
- read-only JSON endpoints for dashboard data
- one narrow companion control endpoint for `mute/unmute`

### Data Layer

Add a small dashboard service module responsible for collecting and shaping:

- companion/runtime state from store kv-state and existing health helpers
- pending approvals count
- folder summaries for selected `agent-office` directories
- previews from `MEMORY.md`, `00_inbox/inbox.md`, and today's daily note
- recent log summaries from `90_logs`

This module should avoid broad filesystem traversal and stay scoped to known `agent-office` paths.

### Authentication

Reuse the existing admin bearer-token auth model. The dashboard should sit behind the same auth boundary as the protected admin routes.

### Frontend

Use one lightweight HTML page with small vanilla JavaScript for polling and rendering. Avoid a frontend framework in v1.

## API Shape

Expected dashboard-facing endpoints:

- `GET /dashboard`
- `GET /dashboard/api/summary`
- `GET /dashboard/api/section/{name}`
- `POST /dashboard/api/companion/mute`
- `POST /dashboard/api/companion/unmute`

The exact paths can shift, but the split should remain:

- one shell page
- one aggregate summary endpoint
- one detail endpoint per section
- one narrow control surface for companion toggles

## Data Included

### Runtime / Companion

- daemon health
- gateway/runtime summary from existing health payloads
- companion last check
- companion last send
- companion skip reason
- companion muted flag
- companion hourly proactive count
- pending approvals count

### Agent-Office Summaries

- `00_inbox`: unchecked count and latest preview
- `10_daily`: today's note existence, modified time, preview
- `60_memory`: topic count, latest topics, `MEMORY.md` preview
- `30_outputs`: recent output files
- `40_resources`: recent resource files
- `90_logs`: recent automation/log activity, recent CSV lines or markdown summary

## Constraints

- Must work as part of the existing service
- Must remain lightweight enough for 24/7 operation
- Must be mobile-usable over Tailscale
- Must not expose broad write access to the filesystem
- Must preserve current admin auth expectations

## Testing

Add tests for:

- protected dashboard routes
- summary payload shape
- section summaries from fixture directories
- companion mute/unmute endpoint behavior
- HTML route availability

Prefer fixture-based tests for `agent-office` scanning instead of reading the live workspace.

## Rollout

Build the dashboard in phases:

1. read-only summary page and JSON endpoints
2. mobile styling and detail views
3. safe companion controls

## Success Criteria

The feature is successful when:

- the existing Apple Flow admin service serves a dashboard page
- the page is usable from a phone over Tailscale
- the page summarizes key `agent-office` folders and memory/log state
- companion mute/unmute works from the page
- the feature remains low-maintenance and does not require a second daemon
