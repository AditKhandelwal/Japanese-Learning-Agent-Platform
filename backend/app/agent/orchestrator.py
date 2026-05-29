"""
Agent orchestrator — drives the ReAct loop with Claude.

Flow:
  1. Build system prompt injected with user's current learning state
  2. Send user message + conversation history to Claude
  3. If Claude returns tool_use blocks, dispatch to tool implementations
  4. Feed tool results back to Claude
  5. Stream final text response to the client
"""

from __future__ import annotations
import json
from typing import AsyncIterator, Optional

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.agent import tools as T

_ALL_TOOLS = [
    {
        "name": "get_review_queue",
        "description": (
            "Returns items due for review, ranked by BKT priority score. "
            "Call this to decide what to practice in a recall session."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "n":          {"type": "integer", "description": "Number of items to return (default 15)"},
                "item_type":  {"type": "string",  "description": "Filter: 'vocab' | 'kanji' | 'grammar' | omit for mixed"},
                "focus_tag":  {"type": "string",  "description": "Optional tag to filter items, e.g. 'te-form'"},
            },
        },
    },
    {
        "name": "get_item_detail",
        "description": "Returns full data for a content item: readings, meanings, examples, tags.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
            },
            "required": ["item_id"],
        },
    },
    {
        "name": "get_weak_patterns",
        "description": (
            "Analyzes the user's error history and returns their top weak pattern tags "
            "(e.g. 'te-form', 'counter-words'). Use after a session or when the user asks why they keep struggling."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lookback_days": {"type": "integer", "description": "How many days of history to analyze (default 14)"},
            },
        },
    },
    {
        "name": "get_next_lesson_topic",
        "description": (
            "Returns the next batch of items to introduce via lesson mode. "
            "Use when the user wants to learn something new or asks what to study next."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_session_stats",
        "description": "Returns accuracy, items reviewed, and p_know deltas for the current session.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "introduce_items",
        "description": (
            "Marks a list of items as introduced in the user's learning record. "
            "Call this after presenting a lesson so items enter the review queue."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of item IDs that were just taught",
                },
            },
            "required": ["item_ids"],
        },
    },
    {
        "name": "grade_response",
        "description": (
            "Record the user's answer and update their BKT knowledge state for that item. "
            "Call this after YOU have evaluated whether the user's answer is correct. "
            "You decide correct=true/false; the tool persists the result and reschedules review. "
            "For fuzzy answers (production, reading), use your judgment — partial credit = correct=true. "
            "Always call this before moving to the next item."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "ID of the item just answered",
                },
                "correct": {
                    "type": "boolean",
                    "description": "True if the user demonstrated knowledge of the item",
                },
                "latency_ms": {
                    "type": "integer",
                    "description": "Approximate response time in ms (estimate based on conversation pace; use 0 if unknown)",
                },
                "user_answer": {
                    "type": "string",
                    "description": "The user's verbatim answer, for the response log",
                },
            },
            "required": ["item_id", "correct", "latency_ms"],
        },
    },
]

_BASE_TONE = """
## Tone
- Warm, encouraging, and concise — this is a learning app, not a lecture
- Keep responses focused — don't over-explain unless asked
- Celebrate progress genuinely but briefly
- If the user asks a grammar question mid-session, answer it, then resume

## Japanese output rules
- Always write kanji with the reading in parentheses the first time it appears: 食べ物（たべもの）
- For example sentences, provide a romaji line underneath so the user can sound it out
- Prefer hiragana over kanji when the kanji is advanced (N3 or higher) unless you are explicitly teaching that kanji
- Never use kanji in exercises without giving the reading — the user may not have studied it yet
"""

_MODE_PROMPTS: dict[str, str] = {
    "lesson": """You are Sensei, an adaptive Japanese language tutor.

## Your role — LESSON mode
Teach new Japanese items the user hasn't seen yet.

## Session flow
1. Call get_next_lesson_topic immediately when the session begins.
2. Choose 3–5 items from the result to teach this session — don't overwhelm.
3. For each item, present it clearly:
   - **Japanese** (kanji/kana) and its **reading** (hiragana/katakana)
   - **Meaning** in English
   - One or two natural **example sentences**
   - A brief **memory tip** or mnemonic when one helps
4. After presenting an item, ask the user a simple check question (e.g., "How would you read 日本語?"). Wait for their reply before moving to the next item.
5. Once all items are covered, call introduce_items with the item IDs you taught so they enter the review queue.
6. Close with a brief session summary (what was learned, when it'll show up in review).

## Rules
- Never dump a raw JSON list at the user — always narrate the lesson.
- Use get_item_detail if you want richer examples for a specific item.
- Do NOT call grade_response in lesson mode — check questions here are low-stakes and ungraded.
""" + _BASE_TONE,

    "production": """You are Sensei, an adaptive Japanese language tutor.

## Your role — PRODUCTION mode
Have the user write sentences using target vocabulary or grammar they've learned.

## Session flow
1. Call get_review_queue (item_type omitted, n=5) to find items the user knows but needs practice with.
2. Pick a target item and ask the user to write a sentence using it. Give context or a prompt if helpful.
3. After the user responds, evaluate their sentence:
   - Is the target word/grammar used correctly?
   - Are particles correct?
   - Is the sentence natural?
4. Call grade_response with correct=true if the core usage is right (allow minor errors), correct=false only for fundamental misuse.
5. Give specific, constructive feedback — show a corrected version if needed.
6. Repeat for 4–6 items.
7. End by calling get_session_stats and summarising.
""" + _BASE_TONE,

    "reading": """You are Sensei, an adaptive Japanese language tutor.

## Your role — READING mode
Present a short Japanese passage and test comprehension.

## Session flow
1. Call get_review_queue (n=15) to see what vocabulary the user knows.
2. Write a 3–5 sentence passage in Japanese using words from that list. Adjust difficulty to N5/N4 level.
3. Show the passage, then ask 2–3 comprehension questions in English.
4. For each question the user answers, call grade_response (correct based on your evaluation).
5. After all questions, explain any vocabulary or grammar points the user found tricky.
6. Close with get_session_stats.
""" + _BASE_TONE,

    "conversation": """You are Sensei, an adaptive Japanese language tutor.

## Your role — CONVERSATION mode
Role-play a scenario in Japanese appropriate to the user's level.

## Session flow
1. Call get_review_queue (n=10) to gauge their vocabulary.
2. Propose a simple scenario (e.g. ordering at a café, asking directions) and start in Japanese.
3. Keep your turns short — let the user practice.
4. When the user makes an error that impedes meaning, gently correct it inline.
5. Use grade_response for key vocabulary moments (correct=true if they used the word naturally).
6. End by calling get_session_stats and naming 1–2 things they did well + 1 thing to work on.
""" + _BASE_TONE,

    "grammar": """You are Sensei, an adaptive Japanese language tutor.

## Your role — GRAMMAR DRILL mode
Teach a grammar point clearly, then reinforce it with fill-in-the-blank exercises.

## Session flow
1. Call get_review_queue (item_type="grammar", n=8) to find grammar items the user should practice.
2. Pick the weakest item (lowest p_know) to focus on first.
3. **Teach it before drilling** — give a mini-lesson on the grammar point:
   - What it means and when to use it
   - The pattern/structure (e.g. Verb-て + ください → polite request)
   - 2–3 natural example sentences showing it in context
   - A memory tip if one helps
4. Then move into drill exercises for that same pattern:
   - Show a sentence with a blank (___) where the grammar pattern goes.
   - Include a brief English hint in parentheses if helpful.
   - Example: "明日、学校___ 行きます。(particle for direction/destination)"
5. For each answer:
   - Accept natural variants, not just one exact answer.
   - Call grade_response immediately after evaluating.
   - Explain WHY the answer is right/wrong and show the full correct sentence.
   - If wrong, give one more try before revealing the answer.
6. After 3–4 exercises on the first point, optionally introduce a second grammar item the same way (teach → drill).
7. After 6–8 total exercises, call get_session_stats and summarise.

## Rules
- Never skip the mini-lesson — the user needs context before drilling.
- One exercise at a time — don't stack multiple blanks in one turn.
- Use get_item_detail if you need the full grammar explanation for an item.
- Keep exercises practical — use vocabulary the user likely knows.
""" + _BASE_TONE,
}

# Fallback for unknown modes
_DEFAULT_PROMPT = """You are Sensei, an adaptive Japanese language tutor.
Use your tools to understand the user's current knowledge state and guide them accordingly.
""" + _BASE_TONE

# Which tools each mode needs (by tool name)
_MODE_TOOLS: dict[str, set[str]] = {
    "lesson":       {"get_next_lesson_topic", "get_item_detail", "introduce_items", "get_session_stats"},
    "grammar":      {"get_review_queue", "get_item_detail", "grade_response", "get_session_stats"},
    "production":   {"get_review_queue", "get_item_detail", "grade_response", "get_session_stats", "get_weak_patterns"},
    "reading":      {"get_review_queue", "get_item_detail", "grade_response", "get_session_stats"},
    "conversation": {"get_review_queue", "grade_response", "get_session_stats", "get_weak_patterns"},
}


def _build_tools(mode: str | None) -> list[dict]:
    allowed = _MODE_TOOLS.get(mode or "", None)
    if allowed is None:
        return _ALL_TOOLS
    return [t for t in _ALL_TOOLS if t["name"] in allowed]


def _build_system(mode: str | None) -> str:
    return _MODE_PROMPTS.get(mode or "", _DEFAULT_PROMPT)


class AgentOrchestrator:
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.history: list[dict] = []

    async def stream(
        self,
        message: str,
        session_id: Optional[str] = None,
        mode=None,
    ) -> AsyncIterator[dict]:
        """
        Run the ReAct loop and yield SSE-compatible dicts:
          {"type": "text",       "content": "..."}
          {"type": "tool_call",  "name": "...", "input": {...}}
          {"type": "tool_result","name": "...", "result": {...}}
          {"type": "done"}
        """
        self.history.append({"role": "user", "content": message})

        while True:
            response = await self.client.messages.create(
                model=settings.claude_smart_model,
                max_tokens=2048,
                system=_build_system(mode),
                tools=_build_tools(mode),
                messages=self.history,
            )

            # Collect assistant content blocks
            assistant_content = []

            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                    yield {"type": "text", "content": block.text}

                elif block.type == "tool_use":
                    assistant_content.append({
                        "type":  "tool_use",
                        "id":    block.id,
                        "name":  block.name,
                        "input": block.input,
                    })
                    yield {"type": "tool_call", "name": block.name, "input": block.input}

            self.history.append({"role": "assistant", "content": assistant_content})

            # If no tool calls, we're done
            if response.stop_reason == "end_turn":
                break

            # Dispatch tool calls and feed results back
            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    result = await self._dispatch(block.name, block.input, session_id)
                    yield {"type": "tool_result", "name": block.name, "result": result}

                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     json.dumps(result),
                    })

                self.history.append({"role": "user", "content": tool_results})

        yield {"type": "done"}

    async def _dispatch(self, name: str, inputs: dict, session_id: Optional[str]) -> dict:
        """Route a tool call to its implementation."""
        match name:
            case "get_review_queue":
                return await T.get_review_queue(
                    db=self.db,
                    user_id=self.user_id,
                    n=inputs.get("n", 15),
                    item_type=inputs.get("item_type"),
                    focus_tag=inputs.get("focus_tag"),
                )
            case "get_item_detail":
                return await T.get_item_detail(self.db, inputs["item_id"])

            case "get_weak_patterns":
                return await T.get_weak_patterns(
                    db=self.db,
                    user_id=self.user_id,
                    lookback_days=inputs.get("lookback_days", 14),
                )
            case "get_next_lesson_topic":
                return await T.get_next_lesson_topic(self.db, self.user_id)

            case "get_session_stats":
                sid = inputs.get("session_id") or session_id
                if not sid:
                    return {"error": "No session_id provided"}
                return await T.get_session_stats(self.db, sid)

            case "introduce_items":
                return await T.introduce_items(self.db, self.user_id, inputs["item_ids"])

            case "grade_response":
                return await T.grade_response(
                    db=self.db,
                    user_id=self.user_id,
                    session_id=session_id or "",
                    item_id=inputs["item_id"],
                    correct=inputs["correct"],
                    latency_ms=inputs.get("latency_ms", 0),
                    user_answer=inputs.get("user_answer", ""),
                )

            case _:
                return {"error": f"Unknown tool: {name}"}
