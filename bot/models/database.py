"""
SQLAlchemy database models for GroupMind bot.

This module defines:
- Group: Telegram group information
- User: User privacy preferences
- Message: Group messages with sentiment
- Summary: Generated summaries with statistics
- Proper relationships, indexes, and soft deletion
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    Float,
    BigInteger,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Group(Base):
    """Telegram group model."""

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(BigInteger, unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    member_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    # Soft deletion
    deleted_at = Column(DateTime, nullable=True, index=True)
    # Bot metadata
    bot_added_at = Column(DateTime, nullable=True)
    bot_removed_at = Column(DateTime, nullable=True)
    
    # Relationships
    messages = relationship(
        "Message",
        back_populates="group",
        cascade="all, delete-orphan",
        foreign_keys="Message.group_id",
    )
    summaries = relationship(
        "Summary",
        back_populates="group",
        cascade="all, delete-orphan",
        foreign_keys="Summary.group_id",
    )

    __table_args__ = (
        Index("idx_group_active_deleted", "is_active", "deleted_at"),
        Index("idx_group_created", "created_at"),
    )

    def soft_delete(self):
        """Soft delete the group."""
        self.is_active = False
        self.deleted_at = datetime.utcnow()

    def restore(self):
        """Restore a soft-deleted group."""
        self.is_active = True
        self.deleted_at = None

    @property
    def is_deleted(self) -> bool:
        """Check if group is soft-deleted."""
        return self.deleted_at is not None

    def __repr__(self):
        return f"<Group(id={self.id}, group_id={self.group_id}, title='{self.title}')>"


class User(Base):
    """Telegram user model with privacy settings."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True, index=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    # Privacy settings
    opt_out = Column(Boolean, default=False, nullable=False, index=True)
    opt_out_reason = Column(String(500), nullable=True)
    opt_out_at = Column(DateTime, nullable=True)
    # Tracking
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)
    # Soft deletion
    deleted_at = Column(DateTime, nullable=True, index=True)

    # Relationships
    messages = relationship(
        "Message",
        back_populates="user",
        foreign_keys="Message.user_id",
    )

    __table_args__ = (
        Index("idx_user_opt_out", "opt_out"),
        Index("idx_user_active", "deleted_at"),
    )

    def opt_out_user(self, reason: Optional[str] = None):
        """Mark user as opted out."""
        self.opt_out = True
        self.opt_out_reason = reason
        self.opt_out_at = datetime.utcnow()

    def opt_in_user(self):
        """Mark user as opted in."""
        self.opt_out = False
        self.opt_out_reason = None
        self.opt_out_at = None

    def soft_delete(self):
        """Soft delete the user."""
        self.deleted_at = datetime.utcnow()

    def restore(self):
        """Restore a soft-deleted user."""
        self.deleted_at = None

    @property
    def is_deleted(self) -> bool:
        """Check if user is soft-deleted."""
        return self.deleted_at is not None

    @property
    def full_name(self) -> str:
        """Get full name of user."""
        name_parts = [self.first_name, self.last_name]
        return " ".join(part for part in name_parts if part)

    def __repr__(self):
        return f"<User(id={self.id}, user_id={self.user_id}, username='{self.username}')>"


class Message(Base):
    """Message model for group messages."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, nullable=False)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Sentiment analysis
    sentiment = Column(String(50), nullable=True)  # positive, negative, neutral, conflict
    sentiment_score = Column(Float, nullable=True)  # -1 to 1
    dominant_emotion = Column(String(50), nullable=True)
    emotion_data = Column(Text, nullable=True)  # JSON
    # Processing metadata
    processed_at = Column(DateTime, nullable=True)
    # Soft deletion
    deleted_at = Column(DateTime, nullable=True, index=True)

    # Relationships
    group = relationship(
        "Group",
        back_populates="messages",
        foreign_keys=[group_id],
    )
    user = relationship(
        "User",
        back_populates="messages",
        foreign_keys=[user_id],
    )

    __table_args__ = (
        UniqueConstraint("group_id", "message_id", name="uq_message_unique_per_group"),
        Index("idx_message_timestamp", "timestamp"),
        Index("idx_message_sentiment", "sentiment"),
        Index("idx_message_group_timestamp", "group_id", "timestamp"),
        Index("idx_message_user_group", "user_id", "group_id"),
        Index("idx_message_deleted", "deleted_at"),
    )

    def soft_delete(self):
        """Soft delete the message."""
        self.deleted_at = datetime.utcnow()

    def restore(self):
        """Restore a soft-deleted message."""
        self.deleted_at = None

    @property
    def is_deleted(self) -> bool:
        """Check if message is soft-deleted."""
        return self.deleted_at is not None

    @property
    def text_preview(self, max_length: int = 100) -> str:
        """Get preview of message text."""
        if len(self.text) <= max_length:
            return self.text
        return self.text[:max_length] + "..."

    def __repr__(self):
        return (
            f"<Message(id={self.id}, message_id={self.message_id}, "
            f"group_id={self.group_id}, user_id={self.user_id}, "
            f"sentiment={self.sentiment})>"
        )


class Summary(Base):
    """Summary model for generated group summaries."""

    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, index=True)
    summary_id = Column(String(255), unique=True, nullable=False, index=True)
    group_id = Column(BigInteger, ForeignKey("groups.group_id"), nullable=False, index=True)
    # Time period covered
    period_start = Column(DateTime, nullable=False, index=True)
    period_end = Column(DateTime, nullable=False, index=True)
    # Summary content
    summary_text = Column(Text, nullable=False)
    # Metadata
    message_count = Column(Integer, default=0)
    participant_count = Column(Integer, default=0)
    sentiment_score = Column(Float, nullable=True)  # Average sentiment (-1 to 1)
    dominant_sentiment = Column(String(50), nullable=True)
    key_topics = Column(Text, nullable=True)  # JSON array
    key_decisions = Column(Text, nullable=True)  # JSON array
    action_items = Column(Text, nullable=True)  # JSON array
    # Processing metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=False)
    processing_time_seconds = Column(Float, nullable=True)
    language = Column(String(10), default="en")
    model_used = Column(String(50), nullable=True)  # deepseek-chat, fallback, etc.
    # Quality metrics
    confidence_score = Column(Float, nullable=True)  # 0 to 1
    is_ai_generated = Column(Boolean, default=False)
    # Soft deletion
    deleted_at = Column(DateTime, nullable=True, index=True)

    # Relationships
    group = relationship(
        "Group",
        back_populates="summaries",
        foreign_keys=[group_id],
    )

    __table_args__ = (
        Index("idx_summary_period", "period_start", "period_end"),
        Index("idx_summary_group_period", "group_id", "period_start", "period_end"),
        Index("idx_summary_created", "created_at"),
        Index("idx_summary_sentiment", "dominant_sentiment"),
        Index("idx_summary_deleted", "deleted_at"),
    )

    def soft_delete(self):
        """Soft delete the summary."""
        self.deleted_at = datetime.utcnow()

    def restore(self):
        """Restore a soft-deleted summary."""
        self.deleted_at = None

    @property
    def is_deleted(self) -> bool:
        """Check if summary is soft-deleted."""
        return self.deleted_at is not None

    @property
    def duration_days(self) -> int:
        """Get number of days covered by this summary."""
        delta = self.period_end - self.period_start
        return delta.days

    @property
    def summary_preview(self, max_length: int = 150) -> str:
        """Get preview of summary text."""
        if len(self.summary_text) <= max_length:
            return self.summary_text
        return self.summary_text[:max_length] + "..."

    def __repr__(self):
        return (
            f"<Summary(id={self.id}, summary_id='{self.summary_id}', "
            f"group_id={self.group_id}, period={self.period_start} "
            f"to {self.period_end})>"
        )


class Subscription(Base):
    """Subscription model for user billing tiers."""

    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, unique=True, index=True)
    tier = Column(String(50), default="FREE", nullable=False, index=True)  # FREE, PRO, ENTERPRISE
    price_in_stars = Column(Integer, default=0, nullable=False)  # Cost in Telegram Stars (0 for FREE)
    # Subscription lifecycle
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True, index=True)  # NULL for lifetime or annual
    auto_renew = Column(Boolean, default=True, nullable=False)
    # Usage limits for this tier
    summaries_per_month = Column(Integer, default=5, nullable=False)  # Summaries allowed per month
    summaries_used_this_month = Column(Integer, default=0, nullable=False)
    summaries_reset_at = Column(DateTime, nullable=True)  # When monthly limit resets
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship(
        "User",
        foreign_keys=[user_id],
    )
    
    __table_args__ = (
        Index("idx_subscription_tier", "tier"),
        Index("idx_subscription_expires", "expires_at"),
        Index("idx_subscription_reset", "summaries_reset_at"),
    )

    def is_active(self) -> bool:
        """Check if subscription is currently active."""
        if self.tier == "FREE":
            return True
        if self.expires_at is None:
            return True
        return self.expires_at > datetime.utcnow()

    def is_trial_active(self) -> bool:
        """Check if this is an active trial subscription."""
        return self.tier != "FREE" and self.started_at is not None

    def days_until_expiry(self) -> Optional[int]:
        """Get days until subscription expires."""
        if self.expires_at is None:
            return None
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)

    def reset_monthly_limit(self):
        """Reset monthly summary usage."""
        self.summaries_used_this_month = 0
        # Set next reset to same date next month
        from dateutil.relativedelta import relativedelta
        self.summaries_reset_at = datetime.utcnow() + relativedelta(months=1)

    def __repr__(self):
        return (
            f"<Subscription(id={self.id}, user_id={self.user_id}, "
            f"tier='{self.tier}', active={self.is_active()})>"
        )


class Payment(Base):
    """Payment model for tracking Telegram Stars transactions."""

    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    telegram_payment_id = Column(String(255), unique=True, nullable=False, index=True)
    # Payment details
    tier = Column(String(50), nullable=False)  # PRO, ENTERPRISE
    amount_in_stars = Column(Integer, nullable=False)
    status = Column(String(50), default="pending", nullable=False, index=True)  # pending, completed, failed, refunded
    # Telegram payment info
    invoice_id = Column(String(255), nullable=True, index=True)
    # Subscription granted
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True)
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    # Metadata
    currency = Column(String(10), default="XTR", nullable=False)  # Telegram Stars
    is_refunded = Column(Boolean, default=False, nullable=False)
    refunded_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("idx_payment_user", "user_id"),
        Index("idx_payment_status", "status"),
        Index("idx_payment_created", "created_at"),
        Index("idx_payment_tier", "tier"),
    )

    def mark_completed(self):
        """Mark payment as completed."""
        self.status = "completed"
        self.completed_at = datetime.utcnow()

    def mark_failed(self):
        """Mark payment as failed."""
        self.status = "failed"

    def mark_refunded(self):
        """Mark payment as refunded."""
        self.is_refunded = True
        self.refunded_at = datetime.utcnow()
        self.status = "refunded"

    def __repr__(self):
        return (
            f"<Payment(id={self.id}, user_id={self.user_id}, "
            f"tier='{self.tier}', status='{self.status}', "
            f"amount={self.amount_in_stars} stars)>"
        )


class AuditLog(Base):
    """Audit log for tracking bot actions."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(100), nullable=False, index=True)  # e.g., "summary_generated", "user_opted_out"
    entity_type = Column(String(50), nullable=False)  # e.g., "group", "user", "message", "summary"
    entity_id = Column(String(50), nullable=False)
    user_id = Column(BigInteger, nullable=True, index=True)  # User who triggered action, if applicable
    details = Column(Text, nullable=True)  # JSON with additional context
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("idx_audit_action_entity", "action", "entity_type"),
        Index("idx_audit_created", "created_at"),
    )

    def __repr__(self):
        return (
            f"<AuditLog(id={self.id}, action='{self.action}', "
            f"entity={self.entity_type}:{self.entity_id})>"
        )


# Export all models
__all__ = [
    "Base",
    "Group",
    "User",
    "Message",
    "Summary",
    "Subscription",
    "Payment",
    "AuditLog",
]
