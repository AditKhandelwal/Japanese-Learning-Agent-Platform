"""
Agent tool implementations.
Each function is called by the orchestrator when Claude requests a tool use.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.db.models import UserItemState, Item, Response, Session
from app.ml import knowledge_tracing as kt


# ---------------------------------------------------------------------------
# Tool: get_review_queue
# ---------------------------------------------------------------------------

async def get_review_queue(
    db: AsyncSession,
    user_id: str,
    n: int = 15,
    item_type: Optional[str] = None,
    focus_tag: Optional[str] = None,
    exclude_kana: bool = False,
    jlpt_level: Optional[str] = None,
    ignore_due: bool = False,
) -> dict:
    """Return top-N items due for review, ranked by BKT priority score."""
    query = (
        select(UserItemState, Item)
        .join(Item, UserItemState.item_id == Item.id)
        .where(UserItemState.user_id == user_id)
        .where(UserItemState.introduced == True)  # noqa: E712
    )
    if item_type:
        query = query.where(Item.type == item_type)
    if exclude_kana:
        query = query.where(~Item.jlpt_level.in_(["hiragana", "katakana"]))
    if jlpt_level:
        query = query.where(Item.jlpt_level == jlpt_level)

    result = await db.execute(query)
    rows = result.all()

    now = datetime.now(timezone.utc)
    scored = []
    for state, item in rows:
        if not ignore_due and state.next_review_due and state.next_review_due > now:
            continue

        if focus_tag and focus_tag not in (item.tags or []):
            continue

        bkt_state = _db_to_bkt(state)
        score = kt.priority_score(bkt_state)
        scored.append((state, item, score))

    _LEVEL_ORDER = {"hiragana": 0, "katakana": 1, "N5": 2, "N4": 3, "N3": 4, "N2": 5, "N1": 6}
    scored.sort(key=lambda x: (_LEVEL_ORDER.get(x[1].jlpt_level, 7), -x[2]))
    top = scored[:n]

    return {
        "items": [
            {
                "item_id":       item.id,
                "japanese":      item.japanese,
                "reading":       item.reading,
                "meaning":       item.meaning,
                "type":          item.type,
                "jlpt_level":    item.jlpt_level,
                "tags":          item.tags or [],
                "p_know":        round(state.p_know, 3),
                "priority_score": round(score, 3),
                "review_count":  state.review_count,
            }
            for state, item, score in top
        ],
        "total_due": len(scored),
    }


# ---------------------------------------------------------------------------
# Tool: get_item_detail
# ---------------------------------------------------------------------------

async def get_item_detail(db: AsyncSession, item_id: str) -> dict:
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        return {"error": f"Item {item_id} not found"}

    return {
        "item_id":    item.id,
        "japanese":   item.japanese,
        "reading":    item.reading,
        "meaning":    item.meaning,
        "type":       item.type,
        "jlpt_level": item.jlpt_level,
        "tags":       item.tags or [],
        "examples":   item.examples or [],
        "extra":      item.extra or {},
    }


# ---------------------------------------------------------------------------
# Tool: get_weak_patterns
# ---------------------------------------------------------------------------

async def get_weak_patterns(
    db: AsyncSession,
    user_id: str,
    lookback_days: int = 14,
    top_n: int = 3,
) -> dict:
    """Identify tags the user consistently misses."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    result = await db.execute(
        select(Response, Item)
        .join(Item, Response.item_id == Item.id)
        .where(Response.user_id == user_id)
        .where(Response.created_at >= cutoff)
        .where(Response.correct == False)  # noqa: E712
    )
    rows = result.all()

    tag_miss: dict[str, list[str]] = {}
    for response, item in rows:
        for tag in (item.tags or []):
            tag_miss.setdefault(tag, [])
            tag_miss[tag].append(item.japanese)

    # Sort by miss count
    sorted_tags = sorted(tag_miss.items(), key=lambda x: len(x[1]), reverse=True)
    patterns = [
        {
            "tag":           tag,
            "miss_count":    len(items),
            "example_items": list(set(items))[:3],
        }
        for tag, items in sorted_tags[:top_n]
    ]

    return {"weak_patterns": patterns, "lookback_days": lookback_days}


# ---------------------------------------------------------------------------
# Tool: get_next_lesson_topic
# ---------------------------------------------------------------------------

async def get_next_lesson_topic(db: AsyncSession, user_id: str) -> dict:
    """
    Find the next item or group of items to introduce via lesson mode.
    Returns the lowest JLPT level that has unintroduced items.
    """
    LEVEL_ORDER = ["hiragana", "katakana", "N5", "N4", "N3", "N2", "N1"]

    for level in LEVEL_ORDER:
        # Check if there are items at this level not yet introduced for this user
        introduced_ids_result = await db.execute(
            select(UserItemState.item_id)
            .where(UserItemState.user_id == user_id)
            .where(UserItemState.introduced == True)  # noqa: E712
        )
        introduced_ids = {row[0] for row in introduced_ids_result.all()}

        unintroduced = await db.execute(
            select(Item)
            .where(Item.jlpt_level == level)
            .where(~Item.id.in_(introduced_ids))
            .limit(5)
        )
        items = unintroduced.scalars().all()

        if items:
            return {
                "level":        level,
                "items_to_introduce": [
                    {
                        "item_id":  i.id,
                        "japanese": i.japanese,
                        "reading":  i.reading,
                        "meaning":  i.meaning,
                        "type":     i.type,
                        "tags":     i.tags or [],
                        "examples": (i.examples or [])[:2],
                    }
                    for i in items
                ],
            }

    return {"message": "All items have been introduced. Great work!"}


# ---------------------------------------------------------------------------
# Tool: get_session_stats
# ---------------------------------------------------------------------------

async def get_session_stats(db: AsyncSession, session_id: str) -> dict:
    result = await db.execute(
        select(Response).where(Response.session_id == session_id)
    )
    responses = result.scalars().all()

    if not responses:
        return {"items_reviewed": 0, "accuracy": 0.0, "avg_latency_ms": 0}

    total   = len(responses)
    correct = sum(1 for r in responses if r.correct)
    avg_lat = int(sum(r.latency_ms or 0 for r in responses) / total)

    p_know_deltas = [
        {
            "item_id": r.item_id,
            "before":  round(r.p_know_before or 0, 3),
            "after":   round(r.p_know_after  or 0, 3),
        }
        for r in responses
    ]

    return {
        "items_reviewed":  total,
        "correct":         correct,
        "accuracy":        round(correct / total, 3),
        "avg_latency_ms":  avg_lat,
        "p_know_deltas":   p_know_deltas,
    }


# ---------------------------------------------------------------------------
# Tool: introduce_items
# ---------------------------------------------------------------------------

async def introduce_items(
    db: AsyncSession,
    user_id: str,
    item_ids: list[str],
) -> dict:
    """Mark items as introduced (sets introduced=True and initial p_know)."""
    import uuid
    from datetime import timedelta

    introduced = []
    for item_id in item_ids:
        item_result = await db.execute(select(Item).where(Item.id == item_id))
        item = item_result.scalar_one_or_none()
        if not item:
            continue

        state_result = await db.execute(
            select(UserItemState).where(
                and_(UserItemState.user_id == user_id, UserItemState.item_id == item_id)
            )
        )
        existing = state_result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if not existing:
            initial = kt.initial_state(item_id, item.jlpt_level)
            db.add(UserItemState(
                id=str(uuid.uuid4()),
                user_id=user_id,
                item_id=item_id,
                p_know=initial.p_know,
                introduced=True,
                next_review_due=now + timedelta(hours=4),   # first review in 4 hours
                updated_at=now,
            ))
            introduced.append(item_id)
        elif not existing.introduced:
            existing.introduced = True
            existing.updated_at = now
            introduced.append(item_id)

    await db.commit()
    return {"introduced": introduced, "count": len(introduced)}


# ---------------------------------------------------------------------------
# Tool: grade_response
# ---------------------------------------------------------------------------

async def grade_response(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    item_id: str,
    correct: bool,
    latency_ms: int,
    user_answer: str = "",
) -> dict:
    """
    Update BKT state after Claude evaluates a user's answer.
    Creates a Response record and updates UserItemState.p_know + next_review_due.
    """
    import uuid

    item_result = await db.execute(select(Item).where(Item.id == item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        return {"error": f"Item {item_id} not found"}

    state_result = await db.execute(
        select(UserItemState).where(
            and_(UserItemState.user_id == user_id, UserItemState.item_id == item_id)
        )
    )
    db_state = state_result.scalar_one_or_none()

    bkt_state = _db_to_bkt(db_state) if db_state else kt.initial_state(item_id, item.jlpt_level)
    p_know_before = bkt_state.p_know
    new_state = kt.update(bkt_state, correct, latency_ms)

    now = datetime.now(timezone.utc)
    if db_state:
        db_state.p_know          = new_state.p_know
        db_state.review_count    = new_state.review_count
        db_state.correct_count   = new_state.correct_count
        db_state.correct_streak  = new_state.correct_streak
        db_state.avg_latency_ms  = new_state.avg_latency_ms
        db_state.last_reviewed   = new_state.last_reviewed
        db_state.next_review_due = new_state.next_review_due
        db_state.updated_at      = now
    else:
        db.add(UserItemState(
            id=str(uuid.uuid4()),
            user_id=user_id,
            item_id=item_id,
            p_know=new_state.p_know,
            review_count=new_state.review_count,
            correct_count=new_state.correct_count,
            correct_streak=new_state.correct_streak,
            avg_latency_ms=new_state.avg_latency_ms,
            last_reviewed=new_state.last_reviewed,
            next_review_due=new_state.next_review_due,
            introduced=True,
            updated_at=now,
        ))

    db.add(Response(
        id=str(uuid.uuid4()),
        session_id=session_id,
        user_id=user_id,
        item_id=item_id,
        correct=correct,
        user_answer=user_answer,
        latency_ms=latency_ms,
        p_know_before=p_know_before,
        p_know_after=new_state.p_know,
        created_at=now,
    ))
    await db.commit()

    return {
        "item_id":        item_id,
        "correct":        correct,
        "p_know_before":  round(p_know_before, 3),
        "p_know_after":   round(new_state.p_know, 3),
        "next_review_due": new_state.next_review_due.isoformat(),
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _db_to_bkt(state: UserItemState) -> kt.ItemKnowledgeState:
    return kt.ItemKnowledgeState(
        item_id=state.item_id,
        p_know=state.p_know,
        review_count=state.review_count,
        correct_count=state.correct_count,
        correct_streak=state.correct_streak,
        avg_latency_ms=state.avg_latency_ms,
        last_reviewed=state.last_reviewed,
        next_review_due=state.next_review_due,
    )
