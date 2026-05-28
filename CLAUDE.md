# Japanese Learning Agent — CLAUDE.md

## Project Overview
An agentic Japanese learning application that combines Bayesian Knowledge Tracing (BKT)
with a Claude-powered LLM agent. The agent adapts lessons dynamically based on a
persistent learner model — separating it from static flashcard apps like Anki.

**The core insight:** Knowledge belongs to the ITEM, not the mode. If a user sees
a word in Lesson mode, then Story mode, then Production mode — all three update the
same p_know for that item. Modes are different lenses on the same item pool.

**Two-layer intelligence:**
- BKT (math layer) — tracks p_know per (user, item), schedules reviews, updates after answers
- Claude (decision layer) — reads p_know via tools, decides what to teach, grades answers

---

## Current State

### Done
- BKT update logic (`knowledge_tracing.py`)
- Database models — 5 tables (Item, User, UserItemState, Session, Response)
- Agent orchestration layer with ReAct loop (`orchestrator.py`)
- 6 agent tools (`tools.py`)
- FastAPI routers: `/api/users`, `/api/assessment`, `/api/chat`, `/api/sessions`
- Supabase JWT auth
- Frontend: Login, Onboarding, Dashboard pages (React + Vite)
- Data ingestion pipeline (vocab, kanji, grammar CSVs)

### In Progress / What's Left (in build order)
1. **Chat UI** — SSE consumer + message rendering (prerequisite for everything)
2. **grade_response tool** — Claude calls this to update BKT mid-session
3. **Vocab/Recall mode** — simplest grading loop, flashcard-style
4. **Lesson mode** — no grading, Claude calls `introduce_items`
5. **Kanji mode** — identical to Vocab, filter `item_type="kanji"`
6. **Grammar Drill** — Claude prompts a pattern, grades fill-in answer
7. **Story/Reading mode** — passage + comprehension, Claude grades understanding
8. **Production mode** — sentence writing, Claude grades with a rubric
9. **Unlock logic** — dashboard locks modes based on BKT thresholds

---

## Architecture

### Stack
- **Frontend:** React + Vite (TypeScript), Supabase auth
- **Backend:** FastAPI (Python), async SQLAlchemy, PostgreSQL (Supabase)
- **Agent:** Claude Sonnet 4.6 (lessons/conversation) + Haiku 4.5 (grading/tool calls)
- **ML:** Custom BKT implementation

### File Structure
```
japanese-learning-agent/
├── frontend/
│   └── src/
│       ├── App.tsx                    ← State machine: login→onboard→dashboard→session
│       ├── pages/
│       │   ├── LoginPage.tsx
│       │   ├── OnboardingPage.tsx
│       │   └── DashboardPage.tsx
│       └── lib/
│           ├── api.ts                 ← HTTP/SSE client
│           └── supabase.ts
│
└── backend/
    └── app/
        ├── main.py                    ← FastAPI app, routers, CORS
        ├── core/
        │   ├── config.py              ← Settings, model names
        │   └── auth.py                ← Supabase JWT + JWKS verification
        ├── db/
        │   ├── database.py            ← Async SQLAlchemy engine
        │   └── models.py              ← 5 tables
        ├── models/
        │   └── schemas.py             ← Pydantic schemas
        ├── routers/
        │   ├── user.py
        │   ├── chat.py                ← SSE streaming
        │   ├── session.py             ← /grade endpoint
        │   └── assessment.py          ← Placement CAT
        ├── agent/
        │   ├── orchestrator.py        ← ReAct loop
        │   └── tools.py               ← 6 tools
        └── ml/
            └── knowledge_tracing.py   ← BKT math
```

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `Item` | Curriculum — vocab, kanji, grammar rows |
| `User` | Profile + onboarding answers |
| `UserItemState` | p_know per (user, item) — the core ML state |
| `Session` | One per study session (mode, start, end) |
| `Response` | Every graded answer (correct, latency, p_know delta) |

---

## Agent Tools

| Tool | Purpose |
|------|---------|
| `get_review_queue()` | Items due for review, ranked by priority |
| `get_next_lesson_topic()` | Unintroduced items at user's level |
| `get_item_detail()` | Full data for one item |
| `get_weak_patterns()` | Tags the user keeps getting wrong |
| `introduce_items()` | Marks items as taught, schedules review |
| `get_session_stats()` | Accuracy + p_know deltas for this session |

### Grading — Key Design Decision
Grading should NOT be a separate HTTP call. It should be a **Claude tool**:
```python
grade_response(item_id: str, correct: bool, latency_ms: int)
```
Claude evaluates the user's answer and calls this tool. The tool updates BKT
server-side. This works across all modes — binary for recall, fuzzy for
production (Claude decides), implicit for conversation.

---

## Learning Modes

| Mode | Purpose | Unlocks At |
|------|---------|-----------|
| Vocab | SRS flashcards | Always |
| Kanji | Recognition + breakdown | After kana |
| Lesson | Claude teaches next grammar concept | Always |
| Grammar Drill | Targeted exercises after a lesson | After first lesson |
| Story | Passage + comprehension questions | N5 vocab threshold |
| Production | Write sentences with target items | After basic grammar |
| Conversation | Free chat with corrections | Later |

Each mode = different system prompt + tool subset in `orchestrator.py`.
The grading infrastructure (`grade_response` tool) is shared across all modes.

---

## User Journey
```
Sign up → Onboarding (6 questions) → BKT seeded for ALL items
                                             ↓
                                  Dashboard (pick a mode)
                                             ↓
                                   Chat with the agent
                                             ↓
                            Answer → Claude grades → BKT updates
                                             ↓
                                  p_know changes scheduling
                                  for that item across all modes
```

---

## Key Design Decisions
1. **Agent accesses learner state through tools only** — never direct DB queries
2. **BKT is source of truth** — agent decisions are grounded in mastery estimates
3. **Dual model** — Sonnet 4.6 for rich lessons/conversation, Haiku 4.5 for grading/tool calls
4. **Modes are lenses** — not separate item pools. Same item, same p_know, different presentation
5. **Unlock logic comes last** — needs BKT data from real sessions to be meaningful

---

## What NOT to Do
- Don't add grading as a separate HTTP endpoint — use the `grade_response` tool
- Don't build unlock logic before modes are working
- Don't separate item pools by mode — p_know is per item, shared across modes
