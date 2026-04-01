from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
from datetime import datetime, timezone

from app.db.database import get_db
from app.db.models import User
from app.models.schemas import UserCreate, UserOut, OnboardingCompleteRequest

router = APIRouter()


@router.post("/", response_model=UserOut)
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    user = User(
        id=str(uuid.uuid4()),
        username=body.username,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserOut(id=user.id, username=user.username, onboarding_done=user.onboarding_done)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    placement = (user.onboarding_data or {}).get("placement_level")
    return UserOut(id=user.id, username=user.username, onboarding_done=user.onboarding_done, placement_level=placement)


@router.post("/{user_id}/onboarding")
async def complete_onboarding(
    user_id: str,
    body: OnboardingCompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.onboarding_done = True
    user.onboarding_data = {
        "knows_hiragana":   body.scripts.knows_hiragana,
        "knows_katakana":   body.scripts.knows_katakana,
        "self_assessment":  body.self_assessment.model_dump(),
        "took_assessment":  body.took_assessment,
        "placement_level":  body.placement_level,
    }
    await db.commit()
    return {"status": "ok", "placement_level": body.placement_level}
