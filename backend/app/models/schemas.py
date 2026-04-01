from pydantic import BaseModel
from typing import Optional, List
from enum import Enum


class ItemType(str, Enum):
    vocab = "vocab"
    kanji = "kanji"
    grammar = "grammar"


class JLPTLevel(str, Enum):
    hiragana = "hiragana"
    katakana = "katakana"
    N5 = "N5"
    N4 = "N4"
    N3 = "N3"
    N2 = "N2"
    N1 = "N1"


class SessionMode(str, Enum):
    lesson = "lesson"
    recall = "recall"
    production = "production"
    conversation = "conversation"
    reading = "reading"
    assessment = "assessment"


# --- Onboarding ---

class OnboardingScripts(BaseModel):
    knows_hiragana: bool
    knows_katakana: bool


class OnboardingSelfAssessment(BaseModel):
    vocabulary: int        # 1-10
    grammar: int           # 1-10
    reading: int           # 1-10
    kanji: int             # 1-10
    reported_jlpt: Optional[str] = None


class OnboardingCompleteRequest(BaseModel):
    user_id: str
    scripts: OnboardingScripts
    self_assessment: OnboardingSelfAssessment
    took_assessment: bool
    placement_level: Optional[str] = None


# --- Users ---

class UserCreate(BaseModel):
    username: str


class UserOut(BaseModel):
    id: str
    username: str
    onboarding_done: bool
    placement_level: Optional[str] = None


# --- Chat ---

class ChatRequest(BaseModel):
    user_id: str
    session_id: Optional[str] = None
    message: str
    mode: Optional[SessionMode] = None


# --- Session ---

class SessionStartRequest(BaseModel):
    user_id: str
    mode: SessionMode
    time_budget_minutes: Optional[int] = 15
    focus_tag: Optional[str] = None


class SessionOut(BaseModel):
    id: str
    user_id: str
    mode: str
    started_at: str


class GradeRequest(BaseModel):
    session_id: str
    user_id: str
    item_id: str
    correct: bool
    user_answer: str
    latency_ms: int


class GradeResult(BaseModel):
    item_id: str
    correct: bool
    p_know_before: float
    p_know_after: float
    next_review_due: str
    feedback: str


# --- Items ---

class ItemDetail(BaseModel):
    id: str
    type: ItemType
    japanese: str
    reading: Optional[str]
    meaning: str
    jlpt_level: JLPTLevel
    tags: List[str]
    examples: List[dict]
    extra: Optional[dict]


class ReviewQueueItem(BaseModel):
    item: ItemDetail
    p_know: float
    priority_score: float
    overdue_hours: Optional[float]


# --- Assessment ---

class AssessmentQuestion(BaseModel):
    item_id: str
    japanese: str
    question_type: str   # "reading" | "meaning" | "usage"
    options: Optional[List[str]] = None   # for multiple choice
    difficulty: str      # N5 | N4 | N3 | N2 | N1


class AssessmentAnswer(BaseModel):
    user_id: str
    item_id: str
    answer: str
    latency_ms: int


class PlacementResult(BaseModel):
    estimated_level: str
    scores_by_level: dict
    recommended_start: str


# --- Stats ---

class WeakPattern(BaseModel):
    tag: str
    miss_count: int
    example_items: List[str]


class UserStats(BaseModel):
    user_id: str
    total_items_introduced: int
    total_reviews: int
    overall_accuracy: float
    items_by_level: dict
    weak_patterns: List[WeakPattern]
