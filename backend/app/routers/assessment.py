"""
Adaptive placement assessment (simplified CAT).

Starts at N5 difficulty, steps up on correct answers and down on incorrect.
After 10-15 questions, estimates the user's level per category and
returns initial p_know values for BKT seeding.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import random

from app.db.database import get_db
from app.db.models import Item
from app.ml.knowledge_tracing import estimate_placement_p_know
from app.models.schemas import AssessmentQuestion, AssessmentAnswer, PlacementResult

router = APIRouter()

LEVEL_ORDER = ["N5", "N4", "N3", "N2", "N1"]
MAX_QUESTIONS = 12


@router.get("/question")
async def get_assessment_question(
    current_level: str = "N5",
    seen_ids: str = "",          # comma-separated item ids already used
    db: AsyncSession = Depends(get_db),
) -> AssessmentQuestion:
    excluded = set(seen_ids.split(",")) if seen_ids else set()

    result = await db.execute(
        select(Item)
        .where(Item.jlpt_level == current_level)
        .where(~Item.id.in_(excluded))
        .order_by(func.random())
        .limit(1)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail=f"No items available for level {current_level}")

    return AssessmentQuestion(
        item_id=item.id,
        japanese=item.japanese,
        question_type="meaning",
        difficulty=current_level,
    )


@router.post("/submit")
async def submit_answer(body: AssessmentAnswer, db: AsyncSession = Depends(get_db)):
    """
    Client tracks the full answer history and sends it here at the end.
    Returns the next difficulty level to use.
    """
    # Fetch correct answer
    result = await db.execute(select(Item).where(Item.id == body.item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    correct = body.answer.strip().lower() in item.meaning.lower()
    return {"correct": correct, "meaning": item.meaning}


@router.post("/finalize", response_model=PlacementResult)
async def finalize_assessment(
    answers: list[dict],   # [{item_id, level, correct}, ...]
):
    """
    Takes the full answer history and returns placement results.
    """
    correct_by_level: dict[str, list[int]] = {}
    for ans in answers:
        level = ans["level"]
        correct_by_level.setdefault(level, [0, 0])
        correct_by_level[level][1] += 1
        if ans["correct"]:
            correct_by_level[level][0] += 1

    p_know_by_level = estimate_placement_p_know(
        {lvl: tuple(counts) for lvl, counts in correct_by_level.items()}
    )

    # Derive estimated level: highest level where accuracy >= 60%
    estimated_level = "N5"
    for level in LEVEL_ORDER:
        counts = correct_by_level.get(level, [0, 0])
        if counts[1] > 0 and counts[0] / counts[1] >= 0.60:
            estimated_level = level

    scores = {
        lvl: {
            "correct": correct_by_level.get(lvl, [0, 0])[0],
            "total":   correct_by_level.get(lvl, [0, 0])[1],
            "p_know":  round(p_know_by_level.get(lvl, 0.0), 3),
        }
        for lvl in LEVEL_ORDER
    }

    return PlacementResult(
        estimated_level=estimated_level,
        scores_by_level=scores,
        recommended_start=estimated_level,
    )
