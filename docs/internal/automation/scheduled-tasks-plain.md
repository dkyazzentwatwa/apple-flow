# CLAUDE SCHEDULED TASKS — AGENT OFFICE

===============================================
🧠 EXECUTIVE ASSISTANT — DAILY OPS
===============================================

---
☀️ MORNING BRIEFING — 7:30 AM Daily
---

You are my executive assistant. Generate my morning briefing for today.

1. CALENDAR — Pull today's events from Google Calendar. Flag any back-to-back meetings or gaps under 15 minutes.

2. EMAIL — Search Gmail for unread messages from the last 12 hours. Summarize the top 3 that need action.

3. DAILY NOTE — Read 10_daily/YYYY-MM-DD.md if it exists. List any open items from the daily note.

4. NEWS — Web search: "[MY INDUSTRY] news today". Surface one relevant headline in one sentence.

5. WEATHER — Web search: "weather [MY CITY] today". One-line summary.

Format as 5 labeled sections. Keep each tight — no more than 3 bullets.
End with: "Today's #1 priority:" — your best read based on everything above.

Save to: 10_daily/YYYY-MM-DD-morning.md
Log to: 90_logs/automation-log.md

---
📥 EMAIL TRIAGE — 9:00 AM Daily
---

Search Gmail for all unread emails from the last 24 hours.

Categorize each as:
🔴 ACTION — I need to reply or decide something
🟡 LEAD — potential client or business opportunity
🔵 FYI — info only, no reply needed
⚫ NOISE — newsletter, auto-email, can archive

For every 🔴 ACTION item: write a short draft reply I can edit and send.
For every 🟡 LEAD: note who it's from, what they want, and a suggested next step.

Output as a table: Category | From | Subject | Summary | Draft (if action)

Save to: 10_daily/YYYY-MM-DD-email.md
Log to: 90_logs/automation-log.md

---
🔁 FOLLOW-UP SWEEP — 3:00 PM Daily
---

Scan for follow-up gaps.

1. GMAIL — Search sent mail from the last 10 days. Find emails with no reply received. Flag anything with no response after 3+ days.

2. DAILY NOTE — Read 10_daily/YYYY-MM-DD.md for any manually logged follow-ups.

For each item:
- Who is it with?
- What was the original ask or context?
- How many days since last contact?
- Draft a short follow-up message (2–3 sentences max)

Sort oldest-first.

Append to: 10_daily/followups.md
Update: 10_daily/YYYY-MM-DD.md
Log to: 90_logs/automation-log.md

End with: "X follow-ups need attention today."

---
🌙 EOD WRAP — 5:30 PM Daily
---

Generate my end-of-day wrap.

1. READ 10_daily/YYYY-MM-DD.md — What got done? What's still open?
2. CALENDAR — Pull tomorrow's events from Google Calendar. Any that need prep?
3. EMAIL — Any threads I started today that are still open?
4. WIN — Based on what you see, name one thing that went well today.
5. TOMORROW SETUP — Write a new 10_daily/YYYY-MM-DD.md for tomorrow with carried tasks + calendar-driven tasks pre-populated.

Keep each section to 3 bullets max.
End with: "Tomorrow's first priority:"

Save to: 10_daily/YYYY-MM-DD-eod.md
Log to: 90_logs/automation-log.md


===============================================
📅 WEEKLY RHYTHM
===============================================

---
🚀 MONDAY KICKOFF — 8:00 AM Every Monday
---

It's Monday. Generate my weekly kickoff brief.

1. WEEK AT A GLANCE — Pull this week's Google Calendar. Summarize key meetings, deadlines, heavy days.
2. OPEN TASKS — Read 10_daily/YYYY-MM-DD.md (most recent) and 10_daily/followups.md. What's unresolved from last week?
3. PIPELINE — Search Gmail for "proposal", "quote", "follow up" in the last 14 days. Status of each active deal.
4. BLOCKERS — Any threads, tasks, or decisions that have been sitting more than 5 days?
5. WEEKLY MISSION — One sentence. The most important outcome for this week.

Scan for a recent pattern: read the last 3 files in 10_daily/ and note any recurring theme.

Save to: 10_daily/YYYY-WW-kickoff.md
Log to: 90_logs/automation-log.md

---
📊 FRIDAY REVIEW — 4:00 PM Every Friday
---

Generate my Friday weekly review.

WINS — Read 10_daily/ files from this week. What got done?
CARRIED — What was planned but didn't happen? Note any pattern.
PIPELINE — Search Gmail for proposal/lead activity this week. Any new, progressed, or stalled?
PATTERNS — Based on this week's daily logs, name one friction point that came up more than once.
NEXT WEEK — Pull Monday–Wednesday calendar. What needs prep over the weekend?
PRE-LOAD — Write 3 priority items to 10_daily/YYYY-MM-DD.md for next Monday.

Keep each section short. Total read time: under 5 minutes.

Save to: 10_daily/YYYY-WW-review.md
Log to: 90_logs/automation-log.md

---
🧘 WEEKLY GTD REVIEW — Sunday 6 PM
---

Run my weekly GTD-style mind sweep and review.

COLLECT
- Read all files modified this week in 10_daily/
- Search Gmail for starred or unread emails
- Pull next week's Google Calendar

PROCESS — For each open item, classify as:
→ ✅ Done
→ ➡️ Next Action (with specific first step)
→ 📅 Scheduled (tied to a date)
→ ⏳ Waiting For (blocked on someone else)
→ 💡 Someday (park it, don't lose it)

REFLECT
- What was the biggest win this week?
- What created the most friction?
- What one habit would have helped?

PLAN
- 3 priorities for next week
- Any deadlines in the next 14 days?
- One thing I should say no to or drop

Append "Someday" items to: 60_memory/someday.md
Write next week's priorities to: 10_daily/YYYY-MM-DD.md
Save full review to: 10_daily/YYYY-WW-gtd.md
Log to: 90_logs/automation-log.md


===============================================
💰 SALES & PIPELINE
===============================================

---
🎯 LEAD PIPELINE REVIEW — Tue & Thu 10:00 AM
---

Run a lead pipeline review.

1. READ 40_resources/pipeline/leads.md — list of active leads with last contact date.
If file doesn't exist, create it with headers: Name | Company | Status | Last Contact | Notes

2. GMAIL — Search for emails containing "proposal", "quote", "scope", "interested", "work together" from the last 30 days.
Cross-reference with leads.md. Add any new contacts not already logged.

3. FLAG — Any lead not contacted in 5+ days gets a 🔴 Cold tag.

4. DRAFT — For the 2 coldest leads, write a short re-engagement email (under 80 words, specific, no fluff).

5. UPDATE — Rewrite 40_resources/pipeline/leads.md with current status for all leads.

End with: "X leads active. X need attention. X warm."
Log to: 90_logs/automation-log.md

---
📬 COLD OUTREACH BATCH — Tuesday 8 AM
---

Generate a batch of 5 cold outreach email drafts for [YOUR ICP / INDUSTRY].

For each prospect:
1. Web search: "[business type] [city/region]" — find a real business to target
2. Web search: "[business name]" — find one specific detail to personalize the opener
3. Draft a cold email:
   - Subject: specific, not salesy, under 8 words
   - Opener: one sentence referencing something real about them
   - Value prop: one sentence on what you do and the outcome it creates
   - CTA: low friction ("worth a quick call?")
   - Length: under 90 words total

Save all 5 drafts as Gmail drafts.
Log to: 40_resources/pipeline/outreach-log.md (create if needed)
Log to: 90_logs/automation-log.md

---
📋 PROPOSAL STATUS AUDIT — Friday 11 AM
---

Audit all open proposals and quotes.

1. GMAIL — Search sent mail for "proposal", "quote", "scope of work", "contract" in the last 45 days.
2. FILESYSTEM — Read 40_resources/pipeline/proposals.md for any manually tracked proposals. Create if needed.

For each open proposal:
- Who is it for?
- Sent date
- Last reply received (if any)
- Days since last contact
- Current status

Tier each as:
🔴 HOT — engaged, likely to close
🟡 WARM — some engagement, needs a nudge
❄️ COLD — no response in 7+ days

Write one follow-up draft for the top 🔴 and one re-engagement for the oldest ❄️.

Update: 40_resources/pipeline/proposals.md
Log to: 90_logs/automation-log.md


===============================================
📣 MARKETING & CONTENT
===============================================

---
✍️ WEEKLY CONTENT IDEAS — Monday 9 AM
---

Generate 7 content ideas for this week about [YOUR NICHE/TOPIC].

For each idea:
- Platform: LinkedIn / Twitter/X / Newsletter / Blog / Short video
- Hook: The opening line or title
- Format: list / story / opinion / tutorial / case study
- Core takeaway: One sentence — what will the reader learn or feel?
- Effort: Low / Medium / High

Research: Web search "[your niche] trending this week" — use at least 2 timely angles.
Also search "[your niche] common mistakes" for evergreen angles.

Check 40_resources/content/used-ideas.md — don't repeat anything from the last 30 days. Create if needed.

Save ideas to: 40_resources/content/ideas-YYYY-WW.md
Log to: 90_logs/automation-log.md

---
📱 LINKEDIN POST DRAFT — Wednesday 8 AM
---

Write a LinkedIn post for this week.

1. Read 40_resources/content/ideas-YYYY-WW.md — pick the strongest idea.
If the file doesn't exist, web search "[your topic] insight this week" and pick an angle.

2. Write the post:
   - Hook line (1 sentence, no question, no "I'm excited to share")
   - 3–5 short paragraphs (no walls of text, max 2 sentences each)
   - One specific number, example, or concrete detail
   - Reader takeaway (what can they do with this?)
   - Subtle CTA — no hard sell
   - 3–5 hashtags max

Tone: direct, specific, first person, no corporate speak.
Length: 150–250 words.

Append to: 40_resources/content/linkedin-drafts.md (create if needed)
Log to: 90_logs/automation-log.md

---
📧 NEWSLETTER DRAFT — Thursday 9 AM
---

Draft this week's newsletter for [YOUR NEWSLETTER].

Audience: [DESCRIBE YOUR READERS]
Tone: [YOUR TONE — e.g. "practical, no fluff, first person"]

Read 40_resources/content/ideas-YYYY-WW.md for this week's content direction.
Web search "[your topic] news this week" for a timely angle.

Structure:
1. OPENER — One observation, story, or thing you noticed this week (2–3 sentences)
2. MAIN PIECE — One useful insight, how-to, or opinion (150–200 words)
3. RESOURCE — One tool, article, or find worth sharing + one sentence on why
4. QUICK TAKE — One hot take in 2 sentences
5. CLOSER — One forward-looking sentence

Give 3 subject line options with different angles.
Write a preview text (1 sentence).

Do NOT use: "In today's newsletter", "Welcome back", "I hope this finds you well"

Save to: 40_resources/content/newsletter-YYYY-MM-DD.md
Log to: 90_logs/automation-log.md

---
🔎 COMPETITOR PULSE — Monday 10 AM
---

Run a quick competitor pulse check.

Search for each of the following and summarize findings in 2–3 sentences each:
1. "[Competitor 1] news OR announcement" — any launches, pricing changes, or updates this week
2. "[Competitor 2] news OR announcement" — same
3. "[Your niche] new tool OR alternative 2025" — any new entrants worth watching
4. "[Your niche] site:reddit.com OR site:news.ycombinator.com" — what are practitioners complaining about?

For each finding:
- What happened
- Why it matters for your positioning
- One action you could take in response (optional)

Read last week's file: 40_resources/research/competitor-YYYY-WW.md
Create research/ folder if needed.

Save to: 40_resources/research/competitor-YYYY-WW.md
Log to: 90_logs/automation-log.md


===============================================
🔬 RESEARCH & INTELLIGENCE
===============================================

---
📡 INDUSTRY SIGNAL MONITOR — Tuesday 7 AM
---

Run my weekly industry signal scan.

Run these 5 searches and summarize each in 2–3 sentences:
1. "[Your industry] funding OR acquisition this week"
2. "[Your topic] product launch OR release 2025"
3. "[Your topic] research OR study 2025"
4. "AI tools [your use case] new"
5. "[Your niche] site:reddit.com OR site:hackernews.com" — community chatter

For each:
- What happened
- Why it matters
- Source quality: High / Medium / Uncertain
- Action for me (if any)

Ignore: podcast episodes, event announcements, opinion fluff.
Prioritize: funding, launches, data, research.

Read 40_resources/research/signals-YYYY-WW.md (last week) — flag if a trend is accelerating.
Save to: 40_resources/research/signals-YYYY-MM-DD.md
Log to: 90_logs/automation-log.md

---
🧩 DEEP RESEARCH BRIEF — On Demand
---

Conduct a deep research brief on: [TOPIC].

Purpose: [Why you're researching — e.g. "evaluating whether to adopt X"]
Context: [Relevant background I should know]

Research plan — run all 5 searches:
1. "[topic] overview OR explainer" — the lay of the land
2. "[topic] problems OR criticisms OR failures" — what goes wrong
3. "[topic] best practices OR case study" — what good looks like
4. "[topic] research paper OR benchmark 2025" — latest data
5. "alternative to [topic]" — what are people doing instead?

Brief structure:
— WHAT IT IS: 1 plain-language paragraph
— WHY IT MATTERS: for my specific context
— KEY PLAYERS: who's doing this well and why
— RISKS & TRAPS: what most people get wrong
— MY RECOMMENDATION: given my context, what should I do?
— TOP 3 LINKS: best sources for further reading

Save to: 40_resources/research/deep/TOPIC-YYYY-MM-DD.md (create deep/ folder if needed)
Log to: 90_logs/automation-log.md

---
👤 PRE-MEETING DOSSIER — 30 min before meetings (On Demand)
---

Build a quick dossier for my meeting with: [PERSON NAME] at [COMPANY].

Meeting purpose: [e.g. sales call / partnership / hiring / investor]

Run these searches:
1. "[Full name] [company]" — role, background, LinkedIn if findable
2. "[Company name]" — what they do, size, recent news
3. "[Full name] interview OR talk OR article" — how they think
4. "[Company name] news 2025" — anything notable happening lately

PERSON
- Current role and tenure
- Career path in 3 bullets
- What they seem to care about most
- Any public content they've created

COMPANY
- What they do and who they serve
- Size and stage
- Recent news
- How they make money

MEETING PREP
- 3 smart questions I could ask
- What they likely want from this meeting
- Any landmines to be aware of

Search Gmail for any prior contact with [name] or [company domain].
Read 10_daily/meetings/ for any prior meeting notes. Create meetings/ folder if needed.

Save to: 10_daily/meetings/YYYY-MM-DD-PERSON.md
Log to: 90_logs/automation-log.md


===============================================
🌱 PERSONAL PRODUCTIVITY
===============================================

---
📚 LEARNING DIGEST — Wednesday 7 PM
---

Generate my weekly learning digest.

Topics I'm currently studying: [LIST YOUR LEARNING TOPICS]

Run 3 searches:
1. "[topic 1] deep dive OR tutorial 2025"
2. "[topic 2] best practices OR case study 2025"
3. "[topic 1 or 2] research OR findings 2025"

For each result:
- Title and source URL
- What you'd learn (2 sentences)
- Estimated read/watch time
- Why it's relevant to what I'm building

Check 30_areas/learning/queue.md — skip anything already there. Create if needed.

Pick the single best resource and write a 3-sentence summary of what I'd gain from it.
Flag with ⭐ PRIORITY if directly applicable to a current project.

Append new resources to: 30_areas/learning/queue.md
Save full digest to: 30_areas/learning/YYYY-WW.md
Log to: 90_logs/automation-log.md

---
⚡ IDEA CAPTURE & TRIAGE — Sunday 8 AM
---

Triage my accumulated idea backlog.

1. Read 00_inbox/inbox.md — unprocessed ideas dropped here during the week
2. Read 60_memory/someday.md — longer-term parked ideas
3. Search Gmail drafts for any unsent notes or ideas to yourself

For each idea:
- State it in one sentence
- Score: Impact (1–5) / Effort (1–5) / Timing (is now the right time?)
- Classify:
  🚀 BUILD NOW — start this week
  📅 SCHEDULE — good idea, not yet
  🗃️ ARCHIVE — interesting but not actionable
  ❌ KILL — let it go

For BUILD NOW items: write the single concrete first step.

Actions:
- Move 🚀 BUILD NOW items to 10_daily/YYYY-MM-DD.md
- Keep 📅 SCHEDULE items in 60_memory/someday.md
- Clear processed items from 00_inbox/inbox.md (don't delete, mark as triaged)

Save triage report to: 40_resources/ideas/triaged-YYYY-MM-DD.md (create ideas/ folder if needed)
End with: "X ideas processed. X worth pursuing."
Log to: 90_logs/automation-log.md

---
🎯 MONTHLY GOAL CHECK-IN — 1st of every month
---

Run my monthly goal check-in.

1. Read 30_areas/goals/active.md — my current goals with targets and timelines.
If it doesn't exist, prompt me to create it after this review.

2. Read the last 4 weekly review files in 10_daily/ — what patterns appear?

3. Search Gmail for any relevant project threads or decisions made this month.

For each goal:
- State the goal and target date
- Status: On Track / At Risk / Off Track / Done
- What happened toward it this month?
- What's blocking progress?
- #1 next action

After reviewing all goals:
- Which goal deserves the most focus next month?
- Is there a goal to officially deprioritize or kill?
- What would make next month a 9/10?

Update: 30_areas/goals/active.md
Save to: 30_areas/goals/YYYY-MM.md
Log to: 90_logs/automation-log.md


===============================================
🔧 DEV & TECHNICAL
===============================================

---
📝 CHANGELOG GENERATOR — Friday 3 PM
---

Generate a changelog entry for [PROJECT NAME].

Read 20_projects/[project]/notes.md for this week's work.
If notes.md doesn't exist, check 20_projects/[project]/ for any markdown files.
If neither exists, I'll paste my notes below.

Format as:
## [version] — today's date

### ✨ New
- [user-facing features added]

### 🔧 Changed
- [existing behavior modified]

### 🐛 Fixed
- [bugs resolved]

### ⚠️ Breaking
- [anything that changes existing interfaces or behavior]

Rules:
- Write from the user/operator perspective, not the code perspective
- One line per item, plain language
- Mark anything experimental with [BETA]
- Skip internal refactors unless they affect behavior

Append to: 20_projects/[project]/CHANGELOG.md (create if needed)
Log to: 90_logs/automation-log.md

[PASTE COMMITS OR NOTES HERE IF NO LOG FILE]

---
🔒 MONTHLY TECH HEALTH CHECK — 1st of every month
---

Run a monthly technical health check across my active projects.

Read 20_projects/ for the list of active projects.

For each project, generate a checklist:
□ Dependency updates needed? (check package.json or requirements.txt age)
□ Any open issues or PRs sitting more than 7 days?
□ Secrets or API keys expiring soon? (check .env.example for references)
□ README accurate and up to date?
□ Any stale branches to clean up?
□ Last deployment or build — when was it?

Web search "[primary framework for each project] security advisory [current month year]" — flag anything critical.

Generate a single prioritized checklist sorted by urgency.

Save to: 30_areas/tech/health-YYYY-MM.md (create tech/ folder if needed)
Log to: 90_logs/automation-log.md

---
🧠 ARCHITECTURE DECISION LOG — On Demand
---

Log an architecture decision record (ADR) based on my notes below.

Format:
# ADR: [Short descriptive title]
Date: [today]
Status: Decided / Proposed / Deprecated / Superseded

## Context
What problem were we solving? What constraints or pressures existed?

## Decision
What did we choose to do?

## Alternatives Considered
What other options did we evaluate and briefly why we didn't choose them?

## Rationale
Why this over the alternatives?

## Consequences
What does this make easier?
What does this make harder or more expensive?

## Review Date
[3 months from today]

Append to: 70_playbooks/adr/index.md (create adr/ folder if needed)
Save full ADR to: 70_playbooks/adr/YYYY-MM-DD-title-slug.md
Log to: 90_logs/automation-log.md

[DESCRIBE YOUR DECISION AND CONTEXT HERE]


===============================================
⚙️ BUSINESS OPS
===============================================

---
💵 MONTHLY REVENUE SNAPSHOT — 1st of every month
---

Generate my monthly revenue snapshot.

GMAIL — Search for:
- "invoice" or "payment received" or "paid" in the last 30 days
- "proposal" or "quote" sent in the last 30 days still open

FILESYSTEM — Read 30_areas/finance/revenue-log.md if it exists.

Compile:
REVENUE IN
- Clients/projects that paid this month (name, amount if visible in email)
- Estimated total

PIPELINE
- Open proposals — estimated value
- Active discussions — rough potential
- Likely to close this month

OUTSTANDING
- Invoices sent but unpaid (with days since sent)
- Anyone overdue?

TREND
- Compare to 30_areas/finance/YYYY-MM.md if it exists
- Revenue up / flat / down?

ONE ACTION
- The single move that would most improve next month's number

Save to: 30_areas/finance/YYYY-MM.md
Update: 30_areas/finance/revenue-log.md (create if needed)
Log to: 90_logs/automation-log.md

---
📋 SOP BUILDER — On Demand
---

Create a Standard Operating Procedure for: [TASK NAME]

I'll describe how I do it — format it as a clean, delegatable SOP.

---
Title: [Clear task name]
Owner: [Who does this]
Frequency: [How often]
Time to complete: [Estimate]
Tools required: [Software, access, accounts needed]
Prerequisites: [What must be true before starting]

Step-by-Step:
1. [Specific, actionable step]
2. ...

Quality Checks:
- How do you know it's done correctly?

Common Mistakes:
- What goes wrong and how to avoid it

Escalation:
- When to ask for help or flag an issue

Automation Opportunity:
- Could any step be automated? How?

Save to: 70_playbooks/TASK-SLUG.md
Append to: 70_playbooks/index.md (create if needed)
Log to: 90_logs/automation-log.md

[DESCRIBE YOUR TASK/PROCESS HERE]

---
📅 QUARTERLY BUSINESS REVIEW — First week of each quarter
---

Run my quarterly business review — Q[X] [YEAR].

FINANCIAL
- Read 30_areas/finance/ for the last 3 months. Revenue trend?
- Best and worst performing service/product this quarter?
- Any overdue invoices or collection issues?

DELIVERY
- Read 10_daily/ reviews for the quarter. What shipped?
- What got deprioritized and why?
- Read 70_playbooks/ — any new systems added?

PIPELINE
- Search Gmail for proposal/lead activity this quarter
- Win rate estimate (deals closed / proposals sent)

MARKET
- Web search "[your industry] trends Q[X] 2025" — what shifted?
- Did any competitors do something notable?

NEXT QUARTER
- Top 3 priorities
- One thing to STOP doing
- One thing to START doing
- Revenue target
- One process or system to build

Save to: 30_areas/ops/qbr-YYYY-QN.md (create ops/ folder if needed)
Log to: 90_logs/automation-log.md


===============================================
👥 COMMUNITY & CREATOR
===============================================

---
💬 COMMUNITY ENGAGEMENT PROMPTS — Monday 8 AM
---

Generate 5 community engagement prompts for [YOUR COMMUNITY TOPIC].

Community: [NAME + 1 sentence description]

For each prompt:
- The prompt itself (1–2 sentences max)
- Format: Question / Challenge / Poll / Show-and-tell / Hot take
- Goal: What response does this encourage?
- Platform: [Slack / Discord / Circle / LinkedIn / Forum]

Mix:
- 1 controversial opinion to react to
- 1 practical question ("what's your go-to tool for X?")
- 1 show-and-tell ("share what you shipped this week")
- 1 quick poll
- 1 teaching moment prompt

Web search "[community topic] debate OR controversy this week" — make at least 1 prompt timely.

Check 40_resources/community/used-prompts.md — don't repeat recent ones. Create if needed.
Append used prompts to: 40_resources/community/used-prompts.md
Save to: 40_resources/community/prompts-YYYY-WW.md (create community/ folder if needed)
Log to: 90_logs/automation-log.md

---
📊 COMMUNITY HEALTH REPORT — 1st of every month
---

Generate my monthly community health report for [COMMUNITY NAME].

I'll provide metrics — you analyze and format them.

Sections:
1. HEALTH SCORE — 1–10 with one-sentence justification
2. GROWTH — New members vs last month. Trend?
3. ENGAGEMENT — Active members (posted or reacted). Any notable drops?
4. TOP TOPICS — What discussions got the most traction?
5. AT-RISK MEMBERS — Anyone who was active before and has gone quiet?
6. WHAT'S WORKING — 2–3 things driving participation
7. WHAT'S NOT — 2–3 friction points or warning signs
8. NEXT MONTH — One strategic experiment to run

Web search "[community topic] community growth tactics 2025" — include one external idea to test.

Compare to: 40_resources/community/health-YYYY-MM.md (last month)
Save to: 40_resources/community/health-YYYY-MM.md (create community/ folder if needed)
Log to: 90_logs/automation-log.md

[PASTE YOUR METRICS HERE]


===============================================
START WITH 3 TASKS
===============================================

Morning Briefing + Follow-Up Sweep + Friday Review.

Let that run for 2 weeks. Then add more.
