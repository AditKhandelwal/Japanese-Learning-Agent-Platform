from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, and_
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.db.database import get_db
from app.db.models import User, Item, UserItemState
from app.models.schemas import UserOut, OnboardingCompleteRequest
from app.core.auth import get_current_user_id, verify_token
from app.ml.knowledge_tracing import seed_p_know_from_onboarding
from app.db.models import new_uuid

_KANA_LEVELS = ("hiragana", "katakana")
_LEVEL_ORDER = case(
    (Item.jlpt_level == "hiragana", 0),
    (Item.jlpt_level == "katakana", 1),
    (Item.jlpt_level == "N5", 2),
    (Item.jlpt_level == "N4", 3),
    (Item.jlpt_level == "N3", 4),
    (Item.jlpt_level == "N2", 5),
    (Item.jlpt_level == "N1", 6),
    else_=7,
)

def _seed_next_review_due(p_know: float, now: datetime) -> datetime | None:
    """Schedule initial review based on seeded p_know so confident items aren't immediately due."""
    if p_know >= 0.90: return now + timedelta(days=7)
    if p_know >= 0.75: return now + timedelta(days=4)
    if p_know >= 0.50: return now + timedelta(days=2)
    if p_know >= 0.30: return now + timedelta(days=1)
    return None  # due immediately — user doesn't know this yet


router = APIRouter()


@router.get("/me", response_model=UserOut)
async def get_or_create_me(
    payload: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    user_id = payload.get("sub")
    username = (payload.get("user_metadata") or {}).get("username") or user_id

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        try:
            user = User(
                id=user_id,
                username=username,
                created_at=datetime.now(timezone.utc),
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        except IntegrityError:
            # Username already taken — append short ID suffix to make it unique
            await db.rollback()
            username = f"{username}_{user_id[:6]}"
            user = User(
                id=user_id,
                username=username,
                created_at=datetime.now(timezone.utc),
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

    placement = (user.onboarding_data or {}).get("jlpt_self_assessment")
    return UserOut(id=user.id, username=user.username, onboarding_done=user.onboarding_done, placement_level=placement)


@router.post("/me/onboarding", response_model=UserOut)
async def complete_onboarding(
    body: OnboardingCompleteRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.onboarding_done = True
    user.onboarding_data = {
        "prior_study":           body.prior_study,
        "knows_hiragana":        body.knows_hiragana,
        "knows_katakana":        body.knows_katakana,
        "kanji_level":           body.kanji_level,
        "jlpt_self_assessment":  body.jlpt_self_assessment,
        "study_frequency":       body.study_frequency,
    }
    await db.commit()

    # Seed BKT knowledge states for all existing items
    items_result = await db.execute(select(Item))
    items = items_result.scalars().all()

    now = datetime.now(timezone.utc)
    for item in items:
        p_know = seed_p_know_from_onboarding(
            jlpt_level=item.jlpt_level,
            knows_hiragana=body.knows_hiragana,
            knows_katakana=body.knows_katakana,
            jlpt_self_assessment=body.jlpt_self_assessment,
        )
        next_due = _seed_next_review_due(p_know, now)
        state = UserItemState(
            id=new_uuid(),
            user_id=user_id,
            item_id=item.id,
            p_know=p_know,
            introduced=True,
            next_review_due=next_due,
        )
        db.add(state)

    await db.commit()
    await db.refresh(user)

    return UserOut(id=user.id, username=user.username, onboarding_done=user.onboarding_done, placement_level=body.jlpt_self_assessment)


@router.get("/me/progress")
async def get_progress(
    item_type: str = Query("vocab"),         # kana | vocab | kanji | grammar
    jlpt_level: Optional[str] = Query(None), # N5 | N4 | ... | hiragana | katakana | None=all
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Return the user's progress across all items of a given type.
    Kana shows all 92 characters regardless of review count.
    Vocab/kanji/grammar show only reviewed items (review_count > 0).
    """
    is_kana = item_type == "kana"

    def _apply_type_filter(q):
        if is_kana:
            return q.where(Item.jlpt_level.in_(_KANA_LEVELS))
        q = q.where(Item.type == item_type)
        q = q.where(~Item.jlpt_level.in_(_KANA_LEVELS))
        return q

    def _apply_level_filter(q):
        if jlpt_level:
            return q.where(Item.jlpt_level == jlpt_level)
        return q

    def _apply_reviewed_filter(q):
        if not is_kana:
            return q.where(UserItemState.review_count > 0)
        return q

    base = (
        select(UserItemState, Item)
        .join(Item, UserItemState.item_id == Item.id)
        .where(UserItemState.user_id == user_id)
    )
    base = _apply_type_filter(base)
    base = _apply_reviewed_filter(base)
    base = _apply_level_filter(base)

    # ── Level stats (aggregated, no pagination) ───────────────────────────
    stats_q = (
        select(
            Item.jlpt_level,
            func.count().label("reviewed"),
            func.avg(UserItemState.p_know).label("avg_p_know"),
            func.sum(case((UserItemState.p_know >= 0.8, 1), else_=0)).label("mastered"),
            func.sum(case((and_(UserItemState.p_know >= 0.5, UserItemState.p_know < 0.8), 1), else_=0)).label("familiar"),
            func.sum(case((and_(UserItemState.p_know >= 0.3, UserItemState.p_know < 0.5), 1), else_=0)).label("learning"),
            func.sum(case((UserItemState.p_know < 0.3, 1), else_=0)).label("weak"),
        )
        .join(Item, UserItemState.item_id == Item.id)
        .where(UserItemState.user_id == user_id)
    )
    stats_q = _apply_type_filter(stats_q)
    stats_q = _apply_reviewed_filter(stats_q)
    stats_q = stats_q.group_by(Item.jlpt_level)
    stats_rows = (await db.execute(stats_q)).all()

    level_stats: dict = {}
    for row in stats_rows:
        level_stats[row.jlpt_level] = {
            "reviewed":  row.reviewed,
            "avg_p_know": round(float(row.avg_p_know or 0), 3),
            "mastered":  int(row.mastered or 0),
            "familiar":  int(row.familiar or 0),
            "learning":  int(row.learning or 0),
            "weak":      int(row.weak or 0),
        }

    # Total items in DB per level (denominator for progress fraction)
    totals_q = (
        select(Item.jlpt_level, func.count().label("total"))
        .group_by(Item.jlpt_level)
    )
    totals_q = _apply_type_filter(totals_q)
    totals_rows = (await db.execute(totals_q)).all()
    for row in totals_rows:
        if row.jlpt_level in level_stats:
            level_stats[row.jlpt_level]["total_items"] = row.total
        else:
            level_stats[row.jlpt_level] = {"total_items": row.total, "reviewed": 0,
                                            "avg_p_know": 0, "mastered": 0,
                                            "familiar": 0, "learning": 0, "weak": 0}

    # ── Paginated items (sorted weakest-first within level) ───────────────
    total_q = select(func.count()).select_from(base.subquery())
    total_reviewed = (await db.execute(total_q)).scalar_one()

    items_q = (
        base
        .order_by(_LEVEL_ORDER, UserItemState.p_know.asc())
        .limit(per_page)
        .offset((page - 1) * per_page)
    )
    rows = (await db.execute(items_q)).all()

    items_out = [
        {
            "item_id":      item.id,
            "japanese":     item.japanese,
            "reading":      item.reading,
            "meaning":      item.meaning[:60],   # trim long meanings
            "type":         item.type,
            "jlpt_level":   item.jlpt_level,
            "p_know":       round(state.p_know, 3),
            "review_count": state.review_count,
        }
        for state, item in rows
    ]

    return {
        "items":          items_out,
        "total_reviewed": total_reviewed,
        "page":           page,
        "per_page":       per_page,
        "level_stats":    level_stats,
    }