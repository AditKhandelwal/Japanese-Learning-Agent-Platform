"""
Bayesian Knowledge Tracing (BKT) implementation.

Each item has 4 parameters:
  p_init  — prior probability the user already knows the item
  p_learn — probability of learning the item after one practice (unknown → known)
  p_slip  — probability of answering incorrectly despite knowing the item
  p_guess — probability of answering correctly without knowing the item

After each response, we update p_know using Bayes' rule then apply the
learning transition. The updated p_know drives spaced-repetition scheduling.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
import math


# Default BKT parameters (research-derived starting values)
DEFAULT_P_INIT   = 0.30
DEFAULT_P_LEARN  = 0.10
DEFAULT_P_SLIP   = 0.10
DEFAULT_P_GUESS  = 0.20

# p_init overrides by JLPT level — easier levels start higher
LEVEL_P_INIT: dict[str, float] = {
    "hiragana": 0.10,
    "katakana": 0.05,
    "N5": 0.40,
    "N4": 0.20,
    "N3": 0.05,
    "N2": 0.02,
    "N1": 0.01,
}

# Scheduling thresholds
SCHEDULE_INTERVALS = [
    (0.90, 10.0),   # p_know >= 0.90 → multiply interval by 10 days base × 2.5
    (0.75, 4.0),
    (0.60, 2.0),
    (0.00, 0.25),   # below 0.60 → review in 6 hours
]
BASE_INTERVAL_DAYS = 1.0
SLOW_ANSWER_THRESHOLD_MS = 5000
SLOW_ANSWER_PENALTY = 0.80  # reduce interval by 20% if answer was slow


@dataclass
class BKTParams:
    p_init:  float = DEFAULT_P_INIT
    p_learn: float = DEFAULT_P_LEARN
    p_slip:  float = DEFAULT_P_SLIP
    p_guess: float = DEFAULT_P_GUESS


@dataclass
class ItemKnowledgeState:
    item_id:         str
    p_know:          float
    review_count:    int = 0
    correct_count:   int = 0
    correct_streak:  int = 0
    avg_latency_ms:  int = 0
    last_reviewed:   Optional[datetime] = None
    next_review_due: Optional[datetime] = None
    params:          BKTParams = field(default_factory=BKTParams)


def initial_state(item_id: str, jlpt_level: str) -> ItemKnowledgeState:
    """Create a fresh BKT state for an item, seeded by JLPT level."""
    p_init = LEVEL_P_INIT.get(jlpt_level, DEFAULT_P_INIT)
    params = BKTParams(p_init=p_init)
    return ItemKnowledgeState(
        item_id=item_id,
        p_know=p_init,
        params=params,
    )


def update(
    state: ItemKnowledgeState,
    correct: bool,
    latency_ms: int,
) -> ItemKnowledgeState:
    """
    Apply one BKT observation and return the updated state.
    Does NOT mutate the input — returns a new state object.
    """
    p = state.params
    p_know = state.p_know

    # 1. Bayesian update: posterior P(know | observation)
    if correct:
        numerator   = p_know * (1.0 - p.p_slip)
        denominator = numerator + (1.0 - p_know) * p.p_guess
    else:
        numerator   = p_know * p.p_slip
        denominator = numerator + (1.0 - p_know) * (1.0 - p.p_guess)

    p_know_given_obs = numerator / denominator if denominator > 0 else p_know

    # 2. Learning transition: P(know after practice)
    p_know_new = p_know_given_obs + (1.0 - p_know_given_obs) * p.p_learn
    p_know_new = min(max(p_know_new, 0.0), 1.0)

    # 3. Update running stats
    new_review_count   = state.review_count + 1
    new_correct_count  = state.correct_count + (1 if correct else 0)
    new_streak         = (state.correct_streak + 1) if correct else 0

    # Running average latency
    prev_avg = state.avg_latency_ms
    new_avg_latency = int(prev_avg + (latency_ms - prev_avg) / new_review_count)

    # 4. Schedule next review
    now = datetime.now(timezone.utc)
    next_due = _schedule_next(p_know_new, correct, latency_ms, now)

    return ItemKnowledgeState(
        item_id=state.item_id,
        p_know=p_know_new,
        review_count=new_review_count,
        correct_count=new_correct_count,
        correct_streak=new_streak,
        avg_latency_ms=new_avg_latency,
        last_reviewed=now,
        next_review_due=next_due,
        params=state.params,
    )


def _schedule_next(
    p_know: float,
    correct: bool,
    latency_ms: int,
    now: datetime,
) -> datetime:
    """Compute next review datetime from updated p_know."""
    multiplier = BASE_INTERVAL_DAYS
    for threshold, mult in SCHEDULE_INTERVALS:
        if p_know >= threshold:
            multiplier = mult
            break

    if not correct:
        # Wrong answer → review soon regardless of p_know
        multiplier = 0.25

    if latency_ms > SLOW_ANSWER_THRESHOLD_MS:
        multiplier *= SLOW_ANSWER_PENALTY

    interval_hours = multiplier * 24.0
    return now + timedelta(hours=interval_hours)


def priority_score(state: ItemKnowledgeState) -> float:
    """
    Higher score = review this item sooner.
    Combines:
      - how overdue the item is
      - how low p_know is (struggling items get a boost)
    """
    now = datetime.now(timezone.utc)

    if state.next_review_due is None:
        overdue_factor = 1.0   # never reviewed → treat as overdue by 1 day
    else:
        hours_overdue = (now - state.next_review_due).total_seconds() / 3600
        overdue_factor = max(hours_overdue / 24.0, 0.0)

    knowledge_gap = 1.0 - state.p_know   # low p_know → higher gap → higher priority

    return overdue_factor * 0.6 + knowledge_gap * 0.4


def bulk_priority(states: list[ItemKnowledgeState]) -> list[tuple[ItemKnowledgeState, float]]:
    """Return (state, priority_score) pairs sorted descending by priority."""
    scored = [(s, priority_score(s)) for s in states]
    return sorted(scored, key=lambda x: x[1], reverse=True)


# p_know seeds by JLPT self-assessment level.
# Each entry covers all levels — lower levels get high p_know if user is advanced.
ONBOARDING_JLPT_SEEDS: dict[str, dict[str, float]] = {
    "unsure": {"N5": 0.10, "N4": 0.05, "N3": 0.02, "N2": 0.01, "N1": 0.01},
    "n5":     {"N5": 0.50, "N4": 0.10, "N3": 0.02, "N2": 0.01, "N1": 0.01},
    "n4":     {"N5": 0.85, "N4": 0.55, "N3": 0.05, "N2": 0.02, "N1": 0.01},
    "n3":     {"N5": 0.90, "N4": 0.85, "N3": 0.55, "N2": 0.05, "N2": 0.02},
    "n2":     {"N5": 0.92, "N4": 0.90, "N3": 0.85, "N2": 0.55, "N1": 0.05},
    "n1":     {"N5": 0.95, "N4": 0.92, "N3": 0.90, "N2": 0.85, "N1": 0.60},
}

ONBOARDING_KANA_SEEDS: dict[str, float] = {
    "yes":      0.90,
    "a_little": 0.45,
    "no":       0.05,
}


def seed_p_know_from_onboarding(
    jlpt_level: str,
    knows_hiragana: str,
    knows_katakana: str,
    jlpt_self_assessment: str,
) -> float:
    """
    Return the initial p_know for a single item given onboarding answers.
    jlpt_level: the item's level (hiragana | katakana | N5 | N4 | N3 | N2 | N1)
    """
    if jlpt_level == "hiragana":
        return ONBOARDING_KANA_SEEDS.get(knows_hiragana, 0.05)
    if jlpt_level == "katakana":
        return ONBOARDING_KANA_SEEDS.get(knows_katakana, 0.05)

    seeds = ONBOARDING_JLPT_SEEDS.get(jlpt_self_assessment.lower(), ONBOARDING_JLPT_SEEDS["unsure"])
    return seeds.get(jlpt_level, DEFAULT_P_INIT)


def estimate_placement_p_know(
    correct_by_level: dict[str, tuple[int, int]]
) -> dict[str, float]:
    """
    Convert adaptive assessment results to initial p_know estimates per level.
    correct_by_level: {level: (correct_count, total_count)}
    Returns: {level: p_know_estimate}
    """
    result = {}
    for level, (correct, total) in correct_by_level.items():
        if total == 0:
            result[level] = LEVEL_P_INIT.get(level, DEFAULT_P_INIT)
        else:
            accuracy = correct / total
            # Blend accuracy with p_init — don't fully trust a 5-question sample
            p_init = LEVEL_P_INIT.get(level, DEFAULT_P_INIT)
            weight = min(total / 10.0, 1.0)   # full trust at 10+ questions
            result[level] = weight * accuracy + (1.0 - weight) * p_init
    return result
