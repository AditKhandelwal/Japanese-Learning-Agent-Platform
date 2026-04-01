from sqlalchemy import (
    Column, String, Float, Integer, Boolean, Text,
    ForeignKey, DateTime, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def new_uuid():
    return str(uuid.uuid4())


class Item(Base):
    __tablename__ = "items"

    id          = Column(String, primary_key=True, default=new_uuid)
    type        = Column(String, nullable=False)       # vocab | kanji | grammar
    japanese    = Column(String, nullable=False)
    reading     = Column(String)                       # furigana / romaji
    meaning     = Column(Text, nullable=False)
    jlpt_level  = Column(String, nullable=False)       # hiragana | katakana | N5-N1
    tags        = Column(JSONB, default=list)           # ["verb", "ichidan", ...]
    examples    = Column(JSONB, default=list)           # [{sentence, translation}, ...]
    extra       = Column(JSONB, default=dict)           # type-specific data

    user_states = relationship("UserItemState", back_populates="item")
    responses   = relationship("Response", back_populates="item")


class User(Base):
    __tablename__ = "users"

    id               = Column(String, primary_key=True, default=new_uuid)
    username         = Column(String, unique=True, nullable=False)
    created_at       = Column(DateTime(timezone=True), default=utcnow)
    onboarding_done  = Column(Boolean, default=False)
    onboarding_data  = Column(JSONB, default=dict)     # placement results, self-assessment

    item_states = relationship("UserItemState", back_populates="user")
    sessions    = relationship("Session", back_populates="user")
    responses   = relationship("Response", back_populates="user")


class UserItemState(Base):
    __tablename__ = "user_item_states"
    __table_args__ = (UniqueConstraint("user_id", "item_id"),)

    id              = Column(String, primary_key=True, default=new_uuid)
    user_id         = Column(String, ForeignKey("users.id"), nullable=False)
    item_id         = Column(String, ForeignKey("items.id"), nullable=False)
    p_know          = Column(Float, nullable=False, default=0.0)
    last_reviewed   = Column(DateTime(timezone=True))
    next_review_due = Column(DateTime(timezone=True))
    review_count    = Column(Integer, default=0)
    correct_count   = Column(Integer, default=0)
    avg_latency_ms  = Column(Integer, default=0)
    correct_streak  = Column(Integer, default=0)
    introduced      = Column(Boolean, default=False)   # taught via lesson mode
    updated_at      = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="item_states")
    item = relationship("Item", back_populates="user_states")


class Session(Base):
    __tablename__ = "sessions"

    id         = Column(String, primary_key=True, default=new_uuid)
    user_id    = Column(String, ForeignKey("users.id"), nullable=False)
    mode       = Column(String, nullable=False)  # lesson|recall|production|conversation|reading|assessment
    started_at = Column(DateTime(timezone=True), default=utcnow)
    ended_at   = Column(DateTime(timezone=True))
    summary    = Column(JSONB, default=dict)     # {items_reviewed, accuracy, p_know_deltas, weak_patterns}

    user      = relationship("User", back_populates="sessions")
    responses = relationship("Response", back_populates="session")


class Response(Base):
    __tablename__ = "responses"

    id            = Column(String, primary_key=True, default=new_uuid)
    session_id    = Column(String, ForeignKey("sessions.id"), nullable=False)
    user_id       = Column(String, ForeignKey("users.id"), nullable=False)
    item_id       = Column(String, ForeignKey("items.id"), nullable=False)
    correct       = Column(Boolean, nullable=False)
    user_answer   = Column(Text)
    latency_ms    = Column(Integer)
    p_know_before = Column(Float)
    p_know_after  = Column(Float)
    created_at    = Column(DateTime(timezone=True), default=utcnow)

    session = relationship("Session", back_populates="responses")
    user    = relationship("User", back_populates="responses")
    item    = relationship("Item", back_populates="responses")
