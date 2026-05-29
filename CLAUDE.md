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
- BKT update logic (`knowledge_tracing.py`) — easy bonus (×1.5), slow-answer penalty (×0.8)
- Database models — 5 tables (Item, User, UserItemState, Session, Response)
- Agent orchestration layer with ReAct loop (`orchestrator.py`)
- 7 agent tools (`tools.py`) — includes `grade_response`
- FastAPI routers: `/api/users`, `/api/assessment`, `/api/chat`, `/api/sessions`
- Supabase JWT auth
- Frontend: Login, Onboarding, Dashboard, SessionPage (chat UI), RecallPage (SRS flashcards)
- Data ingestion pipeline (vocab, kanji, grammar CSVs) — ~57k items seeded
- SRS endpoints: `GET /api/sessions/queue`, `POST /api/sessions/rate`
- **Chat UI** (`SessionPage.tsx`) — SSE streaming, tool call chips, auto-scroll
- **grade_response tool** — Claude calls this to update BKT after evaluating an answer
- **Vocab/Recall mode** — Anki-style SRS flashcards (Again/Hard/Good/Easy)
- **Hiragana & Katakana practice** — same SRS format, persistent BKT per character, "Keep Drilling" overflow option
- Onboarding seeds `next_review_due` from p_know so high-confidence items aren't immediately due
- Queue sorted by JLPT level first (N5 before N1), then BKT priority score

### In Progress / What's Left (in build order)
1. **Lesson mode** — Claude teaches new items, calls `introduce_items()` to mark taught + schedule review
2. **Kanji mode** — same RecallPage, filter `item_type="kanji"`
3. **Kana Guide page** — static content: what kana is, full hiragana/katakana charts, memory tips
4. **Grammar Drill** — Claude prompts a fill-in pattern, grades with `grade_response`
5. **Story/Reading mode** — Claude generates passage, asks comprehension questions
6. **Production mode** — sentence writing, Claude grades with a rubric
7. **Unlock logic** — dashboard locks modes behind BKT thresholds

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
│       ├── App.tsx                    ← State machine: login→onboard→dashboard→session|kana-guide
│       ├── pages/
│       │   ├── LoginPage.tsx
│       │   ├── OnboardingPage.tsx
│       │   ├── DashboardPage.tsx      ← Mode cards + Kana sub-selector modal
│       │   ├── SessionPage.tsx        ← SSE chat UI (Lesson, Grammar Drill, Story, Production)
│       │   └── RecallPage.tsx         ← SRS flashcards (Recall, Hiragana, Katakana, Kanji)
│       └── lib/
│           ├── api.ts                 ← HTTP/SSE client (streamChat, getRecallQueue, rateItem)
│           └── supabase.ts
│
└── backend/
    └── app/
        ├── main.py                    ← FastAPI app, routers, CORS (ports 5173 + 5174)
        ├── core/
        │   ├── config.py              ← Settings, model names
        │   └── auth.py                ← Supabase JWT + JWKS verification
        ├── db/
        │   ├── database.py            ← Async SQLAlchemy engine (pgbouncer compatible)
        │   └── models.py              ← 5 tables
        ├── models/
        │   └── schemas.py             ← Pydantic schemas (SRSRating, SessionMode enum)
        ├── routers/
        │   ├── user.py                ← /me get-or-create, /me/onboarding (seeds BKT)
        │   ├── chat.py                ← SSE streaming endpoint
        │   ├── session.py             ← /queue (SRS due cards), /rate (BKT update), /grade
        │   └── assessment.py          ← Placement CAT
        ├── agent/
        │   ├── orchestrator.py        ← ReAct loop
        │   └── tools.py               ← 7 tools (includes grade_response)
        └── ml/
            └── knowledge_tracing.py   ← BKT math + SRS scheduling
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
| `get_review_queue()` | Items due for review, ranked by JLPT level then BKT priority |
| `get_next_lesson_topic()` | Unintroduced items at user's level |
| `get_item_detail()` | Full data for one item |
| `get_weak_patterns()` | Tags the user keeps getting wrong |
| `introduce_items()` | Marks items as taught, schedules first review |
| `get_session_stats()` | Accuracy + p_know deltas for this session |
| `grade_response()` | Updates BKT after Claude evaluates a user answer |

### Grading — Key Design Decision
Grading is a **Claude tool**, not a separate HTTP endpoint:
```python
grade_response(item_id, correct, latency_ms, user_answer="")
```
Claude evaluates the answer and calls this tool. The tool updates BKT server-side.
Works across all modes — binary for recall, fuzzy for production (Claude decides),
implicit for conversation.

---

## SRS Design — Recall / Kana / Kanji Modes

These modes use `RecallPage.tsx` (no Claude calls) with Anki-style self-rating:

| Rating | correct | latency_ms | easy_bonus | Effect |
|--------|---------|------------|------------|--------|
| Again  | False   | 0          | False      | ~6 hr interval |
| Hard   | True    | 8000       | False      | slow penalty → ~5 hr |
| Good   | True    | 2000       | False      | normal interval |
| Easy   | True    | 500        | True       | ×1.5 interval bonus |

Queue filters (`GET /api/sessions/queue`):
- `exclude_kana=true` — Recall mode (vocab/grammar only)
- `jlpt_level=hiragana|katakana` — Kana practice
- `ignore_due=true` — "Keep Drilling" overflow option (bypasses scheduler)
- `n` — batch size (default 20, kana uses 60)

Queue ordering: JLPT level ascending (hiragana → N5 → N1), then BKT priority score descending.

---

## Learning Modes

| Mode | UI | Purpose | Status |
|------|----|---------|--------|
| Hiragana | RecallPage | SRS for all 46 hiragana | ✅ Done |
| Katakana | RecallPage | SRS for all 46 katakana | ✅ Done |
| Vocab/Recall | RecallPage | SRS for vocab/grammar due items | ✅ Done |
| Lesson | SessionPage | Claude teaches new items, calls `introduce_items` | 🔲 Next |
| Kanji | RecallPage | SRS filtered to `item_type=kanji` | 🔲 Quick |
| Grammar Drill | SessionPage | Fill-in pattern, Claude grades | 🔲 Pending |
| Story/Reading | SessionPage | Passage + comprehension questions | 🔲 Pending |
| Production | SessionPage | Sentence writing + rubric grading | 🔲 Pending |
| Conversation | SessionPage | Free chat with corrections | 🔲 Later |

---

## User Journey
```
Sign up → Onboarding (6 questions) → BKT seeded for ALL items
          (p_know + next_review_due set from self-assessment)
                        ↓
             Dashboard (pick a mode)
                        ↓
         ┌──────────────┴──────────────┐
         ↓                             ↓
   RecallPage                    SessionPage
 (SRS flashcards)            (Claude agent chat)
   Rate card →                 Answer → Claude
  BKT updates                  grades → BKT updates
         └──────────────┬──────────────┘
                        ↓
           p_know changes scheduling for that
           item across ALL modes (shared state)
```

---

## Key Design Decisions
1. **Agent accesses learner state through tools only** — never direct DB queries
2. **BKT is source of truth** — agent decisions are grounded in mastery estimates
3. **Dual model** — Sonnet 4.6 for rich lessons/conversation, Haiku 4.5 for grading/tool calls
4. **Modes are lenses** — not separate item pools. Same item, same p_know, different presentation
5. **SRS timer is shared across modes** — reviewing in Recall pushes next_review_due forward for all modes
6. **Kana uses normal SRS** — not infinite loop. "Keep Drilling" button available when deck is empty
7. **Queue sorted by level first** — easier JLPT levels always surface before harder ones
8. **Unlock logic comes last** — needs BKT data from real sessions to be meaningful

---

## What NOT to Do
- Don't add grading as a separate HTTP endpoint — use the `grade_response` tool
- Don't build unlock logic before modes are working
- Don't separate item pools by mode — p_know is per item, shared across modes
- Don't use `ignore_due=true` by default for kana — that bypasses the BKT scheduler
- Don't show kana characters in Vocab/Recall queue — use `exclude_kana=true`
