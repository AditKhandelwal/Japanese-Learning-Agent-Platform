from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.db.database import get_db
from app.db.models import User, Item, UserItemState
from app.models.schemas import UserOut, OnboardingCompleteRequest
from app.core.auth import get_current_user_id, verify_token
from app.ml.knowledge_tracing import seed_p_know_from_onboarding
from app.db.models import new_uuid

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

    for item in items:
        p_know = seed_p_know_from_onboarding(
            jlpt_level=item.jlpt_level,
            knows_hiragana=body.knows_hiragana,
            knows_katakana=body.knows_katakana,
            jlpt_self_assessment=body.jlpt_self_assessment,
        )
        state = UserItemState(
            id=new_uuid(),
            user_id=user_id,
            item_id=item.id,
            p_know=p_know,
        )
        db.add(state)

    await db.commit()
    await db.refresh(user)

    return UserOut(id=user.id, username=user.username, onboarding_done=user.onboarding_done, placement_level=body.jlpt_self_assessment)