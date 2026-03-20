# iMessage Echo Loop Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop outbound iMessage echoes (especially `attributedBody` fallback rows) from being re-processed as new inbound commands/tasks.

**Architecture:** Keep the current daemon flow, but harden two boundaries: (1) make outbound echo matching tolerant to partial/decoded text fragments, and (2) improve `attributedBody` decoding so we prefer stable human-readable runs over command-token-biased fragments. Validate with targeted regression tests plus full suite.

**Tech Stack:** Python 3.11, pytest, asyncio, SQLite chat.db ingestion, AppleScript-based iMessage egress

---

### Task 1: Add Echo Fragment Regression Test

**Files:**
- Modify: `tests/test_egress.py`
- Test: `tests/test_egress.py`

**Step 1: Write the failing test**

```python
def test_recent_outbound_matches_long_fragment_from_same_send(monkeypatch):
    sent_calls = []

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    egress = IMessageEgress(max_chunk_chars=1200, suppress_duplicate_outbound_seconds=120)
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    full_text = (
        "Here is a long implementation answer that includes task: and project: tokens "
        "but should still be treated as one outbound assistant send. " * 25
    )
    egress.send("+15551234567", full_text)

    fragment = full_text[180:700]  # simulates attributedBody-decoded partial run
    assert egress.was_recent_outbound("+15551234567", fragment) is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_egress.py::test_recent_outbound_matches_long_fragment_from_same_send -v`
Expected: FAIL (fragment not currently matched as recent outbound)

**Step 3: Write minimal implementation**

```python
# In IMessageEgress:
# - Track normalized outbound texts with timestamps.
# - In was_recent_outbound(), after exact fingerprint check, use
#   same-sender containment matching for long normalized strings.
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_egress.py::test_recent_outbound_matches_long_fragment_from_same_send -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_egress.py src/apple_flow/egress.py
git commit -m "fix: suppress attributedBody echo fragments from outbound iMessages"
```

### Task 2: Harden attributedBody Candidate Selection

**Files:**
- Modify: `src/apple_flow/ingress.py`
- Modify: `tests/test_ingress_attributed.py`
- Test: `tests/test_ingress_attributed.py`

**Step 1: Write the failing test**

```python
def test_decode_attributed_body_prefers_long_human_text_over_command_biased_fragment():
    long_text = "this is a long human sentence without command prefix " * 12
    short_command = "task: create project docs"
    blob = (
        b"\\x04\\x0bstreamtyped\\x08NSString\\x01\\x95\\x84\\x01"
        + short_command.encode("ascii")
        + b"\\x86\\x84\\x01\\x95\\x84\\x01"
        + long_text.encode("ascii")
        + b"\\x86\\x84"
    )
    decoded = IMessageIngress._decode_attributed_body(blob)
    assert long_text[:40].strip() in decoded
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingress_attributed.py::test_decode_attributed_body_prefers_long_human_text_over_command_biased_fragment -v`
Expected: FAIL (decoder currently favors command-token fragment)

**Step 3: Write minimal implementation**

```python
# In _decode_attributed_body():
# - Remove heavy command-token bias from scoring.
# - Increase metadata penalties.
# - Prefer longer human-readable runs with whitespace/alpha signals.
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingress_attributed.py::test_decode_attributed_body_prefers_long_human_text_over_command_biased_fragment -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/apple_flow/ingress.py tests/test_ingress_attributed.py
git commit -m "fix: stabilize attributedBody fallback scoring"
```

### Task 3: Verify Poll-Loop Echo Suppression Safety

**Files:**
- Modify: `tests/test_daemon_startup.py`
- Test: `tests/test_daemon_startup.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_poll_loop_ignores_fragment_echo_from_recent_outbound():
    # Arrange daemon with real IMessageEgress marker + inbound fragment message.
    # Assert orchestrator is never called for that row.
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_daemon_startup.py::test_poll_loop_ignores_fragment_echo_from_recent_outbound -v`
Expected: FAIL (fragment currently dispatches to orchestrator)

**Step 3: Write minimal implementation**

```python
# If Task 1 implementation is complete, no daemon code changes may be needed.
# Keep this task to ensure behavior is exercised at poll-loop boundary.
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_daemon_startup.py::test_poll_loop_ignores_fragment_echo_from_recent_outbound -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_daemon_startup.py
git commit -m "test: cover poll-loop suppression of attributedBody echo fragments"
```

### Task 4: Full Verification + Live iMessage Smoke

**Files:**
- Modify: `docs/plans/2026-03-05-imessage-echo-loop-hardening.md` (checklist/status only if needed)
- Test: entire test suite + live runtime logs

**Step 1: Run focused regressions**

Run: `pytest tests/test_egress.py tests/test_ingress_attributed.py tests/test_daemon_startup.py -q`
Expected: PASS

**Step 2: Run full test suite**

Run: `pytest -q`
Expected: PASS

**Step 3: Live send smoke test**

Run:

```bash
PYTHONPATH=src python3 - <<'PY'
from apple_flow.egress import IMessageEgress
egress = IMessageEgress()
egress.send("+15416007167", "[apple-flow smoke] iMessage egress verification")
print("sent")
PY
```

Expected: send succeeds; daemon log shows outbound send and later echo suppression (no recursive task/project handling).

**Step 4: Verify logs show no loop**

Run: `rg -n "Ignoring probable outbound echo|Handled rowid=.*kind=task|Unhandled iMessage dispatch failure" logs/apple-flow.err.log | tail -n 80`
Expected: smoke echo is ignored; no immediate self-triggered task churn from smoke message.

**Step 5: Commit**

```bash
git add src/apple_flow/egress.py src/apple_flow/ingress.py tests/test_egress.py tests/test_ingress_attributed.py tests/test_daemon_startup.py docs/plans/2026-03-05-imessage-echo-loop-hardening.md
git commit -m "fix: harden iMessage echo suppression for attributedBody fallback rows"
```
