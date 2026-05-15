# Rampart: Hands-On Kickoff

This is the operating manual for the next Claude session. Read it top to bottom before touching any file.

## Screenshots

When you hit a UI milestone (auth screen done, dashboard working, etc.), capture a screenshot and save it to `/screenshots/` at the repo root. Use descriptive filenames like `01-job-board.png`, `02-incident-room.png`, `03-audit-chat.png`.

**Embed every screenshot in README.md** via relative markdown image refs: `![Dashboard](screenshots/02-job-board.png)`. A public repo with screenshots embedded in the README is a complete portfolio artifact. **A live deploy URL is optional, not required.** Most viewers who land on the GitHub page see the app in action through the README; that IS the demo.

`/screenshots/` is the one canonical location for source image files. Do not duplicate them into `/docs/` or `/public/`. The README and the portfolio site both reference them from `/screenshots/` (the portfolio-maintainer copies them to the site's public dir at promotion time).

The portfolio-maintainer at `~/projects/portfolio/.claude/agents/portfolio-maintainer.md` looks in `/screenshots/` when deciding whether to promote the project to atifali.pages.dev. No screenshots = the project does not qualify.

## Preflight

Before any code:

1. Docker daemon up: `docker info` returns OK.
2. Ports free: 8040 (api), 5174 (vite), 5456 (postgres), 6382 (redis). Check with `ss -ltn | grep -E '8040|5174|5456|6382'` (should print nothing).
3. Python 3.12 available: `python3.12 --version`.
4. Node 20+ available: `node --version`.
5. Gemini key in `.env` once Phase 4 starts: `GEMINI_API_KEY=...` from Google AI Studio.

## Kickoff prompt for the next session

Paste this into a fresh Claude Code session in `/home/atif/projects/rampart/`:

```
You are picking up Rampart at Phase 1. Read HANDS-ON.md fully, then read docs/ARCHITECTURE.md and docs/ENFORCEMENT_RULES.md. Read the per-project memory at ~/.claude/projects/-home-atif-projects-rampart/memory/MEMORY.md.

Phase 1 goal: implement the FSM engine, audit log, and enforcement engine for ONE job type, happy path only (scheduled -> en_route -> on_site -> work_in_progress -> closeout_pending -> closed). Plus the negative test that proves a closeout without photo + geo + checklist gets rejected by the enforcement engine.

Constraints:
- Deterministic core only. No LLM calls in Phase 1.
- Every state transition writes an audit row in the same DB transaction as the state change.
- Enforcement returns structured decisions (allow/deny/allow_with_override/escalate) with reason codes.
- pytest + pytest-asyncio. Aim for the false-closeout test to fail loudly without the enforcement rule and pass with it.

Do not start Phase 2 in the same session. Commit Phase 1, push, capture screenshots of any CLI or API output, embed in README, stop.
```

## Phase plan

### Phase 0: scaffold (DONE)

- [x] Directory layout (src/{engine,ops,ai,api,schemas}, ui/web, docs, tests, docker)
- [x] README.md, HANDS-ON.md, .gitignore
- [x] docker-compose.yml stub (postgres 16 on 5456, redis 7 on 6382)
- [x] pyproject.toml (Python 3.12, FastAPI, Pydantic v2, google-genai, psycopg, redis)
- [x] FastAPI hello-world at src/api/main.py
- [x] React/Vite shell under ui/web
- [x] Per-project Claude memory dir
- [x] Public GitHub repo at atifali-pm/rampart
- [x] First push

### Phase 1: deterministic core (happy path)

- [ ] Postgres schema: jobs, transitions (audit), enforcement_decisions, overrides
- [ ] FSM declarative definition for the default job lifecycle
- [ ] Guards + side effects framework
- [ ] Enforcement engine: rule catalog + decision function
- [ ] One closeout rule: requires photo + geo within 100m + checklist completed
- [ ] Atomic transition + audit write in single transaction
- [ ] pytest suite: happy path + false-closeout rejection
- [ ] Screenshot of test run, embed in README

### Phase 2: event bus + SLA + dashboard

- [ ] Redis Streams event publisher in the transition hook
- [ ] SLA watcher background task (asyncio) emitting `sla.warning` + `sla.breach`
- [ ] Override capture flow (actor, role, justification, supervisor approval)
- [ ] Escalation ladder configuration
- [ ] React command-centre dashboard: live job board reading from event stream
- [ ] Screenshot: dashboard + escalation flow

### Phase 3: incident command

- [ ] Incident room model: job + events + responders + timeline + chat
- [ ] On-call rotation config
- [ ] Severity-based escalation routing
- [ ] Command bridge view in the dashboard
- [ ] Screenshot: incident room with timeline

### Phase 4: AI layer (Gemini 2.5 Flash)

- [ ] Provider adapter pattern, default Gemini, swappable to Claude
- [ ] Triage agent: incident severity + escalation level from timeline
- [ ] Dispatch agent: tech ranking for a new job
- [ ] Closeout drafter: customer report from work log + photos
- [ ] Audit chat: NL Q&A over audit log + event store
- [ ] Every AI output is recommendation only; humans commit
- [ ] Screenshot: triage recommendation card + audit chat answer

### Phase 5: risk + twin + adversarial tests + promotion

- [ ] Predictive risk score per job
- [ ] Digital operational twin: aggregated live view of sites + techs
- [ ] Adversarial test suite (false closeout, SLA gaming, override abuse)
- [ ] Loom walkthrough or recorded demo
- [ ] Hand off to portfolio-maintainer for case study on atifali.pages.dev
- [ ] Decide on Upwork Catalog + Fiverr surfaces

## Known gotchas

- The deterministic core MUST NOT call any LLM. Keep AI services as separate processes that read the event stream. This protects the "deterministic workflow control" story.
- Audit rows go in the SAME transaction as state changes. If you split them, you have lied about audit integrity.
- Override expiry is not optional. An override with no expiry is a permanent rule change, which defeats the audit story.
- Gemini free tier is 1500 req/day. For portfolio demo traffic this is fine. Do not architect around heavier quotas without re-reading the Google AI Studio limits.
- Ports 5455, 6381, 8030 are taken by Meridian. Stay on 5456, 6382, 8040.

## Visibility rules

- Public from first commit.
- Do not add to atifali.pages.dev until Phase 2 ships.
- Do not add to Upwork Catalog or Fiverr until Phase 4 ships.
- Once promoted, external links use the case-study URL, not the GitHub URL.
