# Agent-Office Web Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a lightweight mobile-friendly web dashboard for `agent-office`, served by the existing Apple Flow admin API, with read-focused summaries and safe companion mute/unmute controls.

**Architecture:** Extend the existing FastAPI app with one HTML route plus a few protected dashboard JSON/action endpoints. Add a small backend module that summarizes scoped `agent-office` folders and companion/store state, and render a simple static HTML/JS mobile-first dashboard on top of those endpoints.

**Tech Stack:** Python 3.11+, FastAPI, existing SQLite store helpers, vanilla HTML/CSS/JavaScript, pytest

---

### Task 1: Add fixture coverage for dashboard summary collection

**Files:**
- Create: `tests/test_dashboard_summary.py`
- Modify: `tests/conftest.py`
- Reference: `src/apple_flow/memory.py`

**Step 1: Write the failing test**

Add tests that build a temporary `agent-office` fixture and assert a future summary function returns:
- inbox unchecked count
- today note existence
- memory topic count
- recent file lists for outputs/resources/logs

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_summary.py -v`
Expected: FAIL because the dashboard summary module does not exist yet.

**Step 3: Write minimal implementation**

Create a backend helper module, likely `src/apple_flow/dashboard.py`, with pure functions that:
- accept `agent-office` path plus store/config context
- scan only the known directories
- compute counts, timestamps, and previews

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_summary.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_dashboard_summary.py tests/conftest.py src/apple_flow/dashboard.py
git commit -m "test: add agent-office dashboard summary coverage"
```

### Task 2: Add runtime and companion status aggregation for the dashboard

**Files:**
- Modify: `src/apple_flow/dashboard.py`
- Test: `tests/test_dashboard_summary.py`
- Reference: `src/apple_flow/orchestrator.py`
- Reference: `src/apple_flow/main.py`

**Step 1: Write the failing test**

Add tests asserting the dashboard summary includes:
- pending approvals count
- companion muted flag
- companion last check
- companion last sent
- companion skip reason

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_summary.py -v`
Expected: FAIL because runtime/companion fields are missing.

**Step 3: Write minimal implementation**

Extend `src/apple_flow/dashboard.py` to read the needed kv-state/store values and package them into a stable summary payload suitable for the UI.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_summary.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/apple_flow/dashboard.py tests/test_dashboard_summary.py
git commit -m "feat: add companion and runtime dashboard summary data"
```

### Task 3: Add protected dashboard API endpoints

**Files:**
- Modify: `src/apple_flow/main.py`
- Modify: `tests/test_admin_api.py`
- Reference: `src/apple_flow/dashboard.py`

**Step 1: Write the failing test**

Add admin API tests covering:
- `GET /dashboard/api/summary`
- `GET /dashboard/api/section/inbox`
- auth enforcement for protected dashboard routes

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_admin_api.py -v`
Expected: FAIL because the routes do not exist yet.

**Step 3: Write minimal implementation**

Add protected FastAPI routes that:
- build dashboard summaries from `agent-office`
- return section-specific payloads
- reuse the existing bearer-token dependency

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_admin_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/apple_flow/main.py tests/test_admin_api.py src/apple_flow/dashboard.py
git commit -m "feat: add protected dashboard api routes"
```

### Task 4: Add companion mute/unmute action endpoints

**Files:**
- Modify: `src/apple_flow/main.py`
- Modify: `tests/test_admin_api.py`

**Step 1: Write the failing test**

Add tests for:
- `POST /dashboard/api/companion/mute`
- `POST /dashboard/api/companion/unmute`
- resulting store kv-state changes

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_admin_api.py -v`
Expected: FAIL because the action endpoints do not exist.

**Step 3: Write minimal implementation**

Add narrow protected endpoints that only toggle `companion_muted` in the store and return the new state.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_admin_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/apple_flow/main.py tests/test_admin_api.py
git commit -m "feat: add dashboard companion control endpoints"
```

### Task 5: Add the HTML dashboard shell

**Files:**
- Create: `src/apple_flow/static/dashboard.html`
- Modify: `src/apple_flow/main.py`
- Modify: `tests/test_admin_api.py`

**Step 1: Write the failing test**

Add a test that requests `GET /dashboard` and asserts:
- `200 OK`
- HTML content type
- a stable title or heading like `Agent Office Dashboard`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_admin_api.py -v`
Expected: FAIL because the HTML route does not exist.

**Step 3: Write minimal implementation**

Serve one static HTML shell from FastAPI that:
- renders a mobile-first layout
- loads summary data from `/dashboard/api/summary`
- exposes tap targets for section cards
- includes buttons for mute/unmute and refresh

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_admin_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/apple_flow/static/dashboard.html src/apple_flow/main.py tests/test_admin_api.py
git commit -m "feat: add agent-office dashboard shell"
```

### Task 6: Add lightweight styling and section-detail rendering

**Files:**
- Modify: `src/apple_flow/static/dashboard.html`
- Test: `tests/test_admin_api.py`

**Step 1: Write the failing test**

Add a minimal HTML test asserting key UI hooks exist:
- runtime status region
- section cards
- action buttons

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_admin_api.py -v`
Expected: FAIL because the HTML shell lacks the expected hooks.

**Step 3: Write minimal implementation**

Enhance the HTML file with:
- mobile-first CSS
- lightweight status cards
- section detail panels or routes
- simple polling/refresh behavior with vanilla JS

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_admin_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/apple_flow/static/dashboard.html tests/test_admin_api.py
git commit -m "feat: add mobile-friendly dashboard rendering"
```

### Task 7: Document dashboard access and Tailscale usage

**Files:**
- Modify: `README.md`
- Modify: `docs/ENV_SETUP.md`
- Optional: `docs/QUICKSTART.md`

**Step 1: Write the failing doc checklist**

Capture the documentation gaps:
- where the dashboard lives
- auth requirements
- mobile/Tailscale access guidance
- safe-action scope

**Step 2: Update the docs**

Add concise docs covering:
- dashboard URL shape
- bearer-token requirement
- how to access it over Tailscale
- what the dashboard can and cannot do in v1

**Step 3: Verify docs are accurate**

Manually cross-check routes and config names against code.

**Step 4: Commit**

```bash
git add README.md docs/ENV_SETUP.md docs/QUICKSTART.md
git commit -m "docs: add agent-office dashboard usage guide"
```

### Task 8: Run focused verification and full regression checks

**Files:**
- No code changes required unless failures are found

**Step 1: Run focused dashboard tests**

Run: `pytest tests/test_dashboard_summary.py tests/test_admin_api.py -v`
Expected: PASS

**Step 2: Run broader regression coverage**

Run: `pytest tests/test_health_dashboard.py tests/test_companion.py tests/test_siri_shortcuts.py -v`
Expected: PASS

**Step 3: Run full suite**

Run: `pytest -q`
Expected: PASS

**Step 4: Final commit if needed**

If verification required fixes:

```bash
git add -A
git commit -m "fix: stabilize agent-office dashboard implementation"
```
