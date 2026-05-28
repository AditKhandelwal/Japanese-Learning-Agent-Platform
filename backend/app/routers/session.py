from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.db.database import get_db
from app.db.models import Session, UserItemState, Item, Response
from app.ml import knowledge_tracing as kt
from app.models.schemas import SessionStartRequest, SessionOut, GradeRequest, GradeResult, SRSRateRequest, SRSRateResult

# Maps SRS self-rating → (correct, latency_ms, easy_bonus)
# latency_ms is used as a proxy for confidence level in the BKT scheduler:
#   hard  → triggers the slow-answer penalty (×0.80 interval)
#   easy  → triggers the easy bonus (×1.50 interval)
_RATING_PARAMS: dict[str, tuple[bool, int, bool]] = {
    "again": (False, 0,    False),
    "hard":  (True,  8000, False),
    "good":  (True,  2000, False),
    "easy":  (True,  500,  True),
}

router = APIRouter()


@router.post("/", response_model=SessionOut)
async def start_session(body: SessionStartRequest, db: AsyncSession = Depends(get_db)):
    session = Session(
        id=str(uuid.uuid4()),
        user_id=body.user_id,
        mode=body.mode.value,
        started_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionOut(
        id=session.id,
        user_id=session.user_id,
        mode=session.mode,
        started_at=session.started_at.isoformat(),
    )


@router.post("/{session_id}/end")
async def end_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.ended_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "ended"}


@router.get("/queue")
async def get_queue(
    user_id: str = Query(...),
    item_type: Optional[str] = Query(None),
    exclude_kana: bool = Query(False),
    jlpt_level: Optional[str] = Query(None),
    ignore_due: bool = Query(False),
    n: int = Query(20),
    db: AsyncSession = Depends(get_db),
):
    """Return items due for SRS review, ranked by BKT priority score."""
    from app.agent import tools as T
    return await T.get_review_queue(
        db, user_id, n=n, item_type=item_type,
        exclude_kana=exclude_kana, jlpt_level=jlpt_level, ignore_due=ignore_due,
    )


@router.post("/rate", response_model=SRSRateResult)
async def rate_item(body: SRSRateRequest, db: AsyncSession = Depends(get_db)):
    """
    Record an Anki-style self-rating (Again/Hard/Good/Easy) and update BKT.
    Maps the rating to correct + latency_ms + easy_bonus, then runs kt.update().
    """
    correct, latency_ms, easy_bonus = _RATING_PARAMS[body.rating]

    item_result = await db.execute(select(Item).where(Item.id == body.item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    state_result = await db.execute(
        select(UserItemState).where(
            and_(UserItemState.user_id == body.user_id, UserItemState.item_id == body.item_id)
        )
    )
    db_state = state_result.scalar_one_or_none()

    if db_state:
        bkt_state = kt.ItemKnowledgeState(
            item_id=body.item_id,
            p_know=db_state.p_know,
            review_count=db_state.review_count,
            correct_count=db_state.correct_count,
            correct_streak=db_state.correct_streak,
            avg_latency_ms=db_state.avg_latency_ms,
            last_reviewed=db_state.last_reviewed,
            next_review_due=db_state.next_review_due,
        )
    else:
        bkt_state = kt.initial_state(body.item_id, item.jlpt_level)

    p_know_before = bkt_state.p_know
    new_state = kt.update(bkt_state, correct, latency_ms, easy_bonus=easy_bonus)

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
            user_id=body.user_id,
            item_id=body.item_id,
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
        session_id=body.session_id,
        user_id=body.user_id,
        item_id=body.item_id,
        correct=correct,
        user_answer=body.rating,   # store the rating label as the "answer"
        latency_ms=latency_ms,
        p_know_before=p_know_before,
        p_know_after=new_state.p_know,
        created_at=now,
    ))
    await db.commit()

    return SRSRateResult(
        item_id=body.item_id,
        rating=body.rating,
        correct=correct,
        p_know_before=round(p_know_before, 3),
        p_know_after=round(new_state.p_know, 3),
        next_review_due=new_state.next_review_due.isoformat(),
    )


@router.post("/grade", response_model=GradeResult)
async def grade_response(body: GradeRequest, db: AsyncSession = Depends(get_db)):
    # Load or create user item state
    state_result = await db.execute(
        select(UserItemState).where(
            and_(UserItemState.user_id == body.user_id, UserItemState.item_id == body.item_id)
        )
    )
    db_state = state_result.scalar_one_or_none()

    # Load item for its jlpt_level
    item_result = await db.execute(select(Item).where(Item.id == body.item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Build BKT state object
    if db_state:
        state = kt.ItemKnowledgeState(
            item_id=body.item_id,
            p_know=db_state.p_know,
            review_count=db_state.review_count,
            correct_count=db_state.correct_count,
            correct_streak=db_state.correct_streak,
            avg_latency_ms=db_state.avg_latency_ms,
            last_reviewed=db_state.last_reviewed,
            next_review_due=db_state.next_review_due,
        )
    else:
        state = kt.initial_state(body.item_id, item.jlpt_level)

    p_know_before = state.p_know

    # Run BKT update
    new_state = kt.update(state, body.correct, body.latency_ms)

    # Persist updated state
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
        db_state = UserItemState(
            id=str(uuid.uuid4()),
            user_id=body.user_id,
            item_id=body.item_id,
            p_know=new_state.p_know,
            review_count=new_state.review_count,
            correct_count=new_state.correct_count,
            correct_streak=new_state.correct_streak,
            avg_latency_ms=new_state.avg_latency_ms,
            last_reviewed=new_state.last_reviewed,
            next_review_due=new_state.next_review_due,
            introduced=True,
            updated_at=now,
        )
        db.add(db_state)

    # Record the response event
    response = Response(
        id=str(uuid.uuid4()),
        session_id=body.session_id,
        user_id=body.user_id,
        item_id=body.item_id,
        correct=body.correct,
        user_answer=body.user_answer,
        latency_ms=body.latency_ms,
        p_know_before=p_know_before,
        p_know_after=new_state.p_know,
        created_at=now,
    )
    db.add(response)
    await db.commit()

    feedback = _feedback_text(body.correct, p_know_before, new_state.p_know)

    return GradeResult(
        item_id=body.item_id,
        correct=body.correct,
        p_know_before=round(p_know_before, 3),
        p_know_after=round(new_state.p_know, 3),
        next_review_due=new_state.next_review_due.isoformat(),
        feedback=feedback,
    )


def _feedback_text(correct: bool, before: float, after: float) -> str:
    delta = after - before
    if correct:
        if after >= 0.90:
            return f"Excellent! p_know {before:.0%} → {after:.0%} ↑  Next review in several days."
        return f"Correct! p_know {before:.0%} → {after:.0%} ↑"
    else:
        return f"Not quite. p_know {before:.0%} → {after:.0%}  Review scheduled soon."
