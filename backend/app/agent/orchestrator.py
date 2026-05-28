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

TOOL_DEFINITIONS = [
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

SYSTEM_PROMPT = """You are Sensei, an adaptive Japanese language tutor powered by a Bayesian Knowledge Tracing model.

## Your role
- Guide the user through Japanese learning sessions tailored to their exact knowledge state
- Use your tools to check what the user needs to review, detect struggle patterns, and decide what to teach next
- Be warm, encouraging, and concise — this is a learning app, not a lecture

## Available modes
- **lesson**: Introduce new vocabulary, kanji, or grammar. Explain clearly, give examples, then introduce items into the review queue.
- **recall**: Flashcard-style review of introduced items. Present the item, wait for the user's answer, then call grade via the frontend.
- **production**: Ask the user to write a sentence using a target word or grammar point. Evaluate their output.
- **conversation**: Role-play a scenario in Japanese appropriate to their level.
- **reading**: Present a short passage using their known vocabulary and ask comprehension questions.

## Reasoning approach
1. When a session starts, call get_review_queue or get_next_lesson_topic to understand what's needed
2. Reason about the results before responding — don't just dump tool output at the user
3. If you notice weak patterns, acknowledge them specifically (e.g. "You've been missing ichidan verb conjugations")
4. At session end, call get_session_stats and give a short, specific summary

## Tone
- Use the user's name if you know it
- Keep responses focused — don't over-explain unless asked
- Celebrate progress genuinely but briefly
- If the user asks a grammar question mid-session, answer it, then resume
"""


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
                system=SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
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
