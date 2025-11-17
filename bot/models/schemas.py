"""
Pydantic schemas for GroupMind bot API and data validation.

This module provides:
- MessageCreate: Validation for incoming messages
- SummaryCreate: Validation for generated summaries
- GroupStats: Statistics for group activity
- API responses and request validation
- Proper field types and validation rules
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field, validator, root_validator


class SentimentType(str, Enum):
    """Sentiment classification."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    CONFLICT = "conflict"
    MIXED = "mixed"


class EmotionType(str, Enum):
    """Emotion classification."""
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    NEUTRAL = "neutral"


class UserBase(BaseModel):
    """Base user schema."""
    user_id: int = Field(..., gt=0, description="Telegram user ID")
    username: Optional[str] = Field(None, min_length=1, max_length=255)
    first_name: Optional[str] = Field(None, min_length=1, max_length=255)
    last_name: Optional[str] = Field(None, min_length=1, max_length=255)

    class Config:
        """Pydantic config."""
        str_strip_whitespace = True


class UserCreate(UserBase):
    """Schema for creating a user."""
    pass


class UserUpdate(BaseModel):
    """Schema for updating user."""
    username: Optional[str] = Field(None, min_length=1, max_length=255)
    first_name: Optional[str] = Field(None, min_length=1, max_length=255)
    last_name: Optional[str] = Field(None, min_length=1, max_length=255)
    opt_out: Optional[bool] = None
    opt_out_reason: Optional[str] = Field(None, max_length=500)

    class Config:
        """Pydantic config."""
        str_strip_whitespace = True


class UserResponse(UserBase):
    """Schema for user response."""
    id: int
    opt_out: bool
    opt_out_reason: Optional[str]
    opt_out_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    last_seen: Optional[datetime]

    class Config:
        """Pydantic config."""
        from_attributes = True


class GroupBase(BaseModel):
    """Base group schema."""
    group_id: int = Field(..., gt=0, description="Telegram group ID")
    title: str = Field(..., min_length=1, max_length=255)
    member_count: int = Field(default=0, ge=0)

    class Config:
        """Pydantic config."""
        str_strip_whitespace = True


class GroupCreate(GroupBase):
    """Schema for creating a group."""
    pass


class GroupUpdate(BaseModel):
    """Schema for updating group."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    member_count: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None

    class Config:
        """Pydantic config."""
        str_strip_whitespace = True


class GroupResponse(GroupBase):
    """Schema for group response."""
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    bot_added_at: Optional[datetime]
    bot_removed_at: Optional[datetime]

    class Config:
        """Pydantic config."""
        from_attributes = True


class MessageBase(BaseModel):
    """Base message schema."""
    text: str = Field(..., min_length=1, max_length=4096, description="Message content")
    timestamp: datetime = Field(..., description="When message was sent")

    class Config:
        """Pydantic config."""
        str_strip_whitespace = True


class MessageCreate(MessageBase):
    """Schema for creating a message."""
    message_id: int = Field(..., gt=0, description="Telegram message ID")
    group_id: int = Field(..., gt=0, description="Telegram group ID")
    user_id: int = Field(..., gt=0, description="Telegram user ID")
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0)
    dominant_emotion: Optional[str] = None

    @validator("text")
    def validate_text(cls, v):
        """Validate message text is not empty."""
        if not v or not v.strip():
            raise ValueError("Message text cannot be empty")
        return v.strip()

    @validator("timestamp")
    def validate_timestamp(cls, v):
        """Validate timestamp is not in the future."""
        if v > datetime.utcnow():
            raise ValueError("Message timestamp cannot be in the future")
        return v


class MessageUpdate(BaseModel):
    """Schema for updating message."""
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0)
    dominant_emotion: Optional[str] = None

    class Config:
        """Pydantic config."""
        str_strip_whitespace = True


class MessageResponse(MessageBase):
    """Schema for message response."""
    id: int
    message_id: int
    group_id: int
    user_id: int
    sentiment: Optional[SentimentType]
    sentiment_score: Optional[float]
    dominant_emotion: Optional[EmotionType]
    emotion_data: Optional[Dict[str, float]]
    processed_at: Optional[datetime]
    created_at: datetime

    class Config:
        """Pydantic config."""
        from_attributes = True


class SentimentAnalysis(BaseModel):
    """Sentiment analysis result."""
    sentiment: SentimentType
    score: float = Field(..., ge=-1.0, le=1.0)
    dominant_emotion: EmotionType
    emotions: Dict[str, float]
    keywords: List[str]
    confidence: float = Field(..., ge=0.0, le=1.0)


class SummaryCreate(BaseModel):
    """Schema for creating a summary."""
    group_id: int = Field(..., gt=0, description="Telegram group ID")
    period_start: datetime = Field(..., description="Start of summary period")
    period_end: datetime = Field(..., description="End of summary period")
    summary_text: str = Field(..., min_length=10, max_length=10000, description="Summary content")
    message_count: int = Field(..., ge=0)
    participant_count: int = Field(..., ge=1)
    sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0)
    dominant_sentiment: Optional[str] = None
    key_topics: Optional[List[str]] = Field(default_factory=list, max_items=10)
    key_decisions: Optional[List[str]] = Field(default_factory=list, max_items=10)
    action_items: Optional[List[str]] = Field(default_factory=list, max_items=10)
    language: str = Field(default="en", min_length=2, max_length=10)
    model_used: Optional[str] = Field(None, max_length=50)
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    is_ai_generated: bool = Field(default=True)
    processing_time_seconds: Optional[float] = Field(None, ge=0.0)

    @root_validator(skip_on_failure=True)
    def validate_period(cls, values):
        """Validate that period_start is before period_end."""
        start = values.get("period_start")
        end = values.get("period_end")
        if start and end and start >= end:
            raise ValueError("period_start must be before period_end")
        return values

    @validator("summary_text")
    def validate_summary_text(cls, v):
        """Validate summary text is meaningful."""
        if not v or not v.strip():
            raise ValueError("Summary text cannot be empty")
        return v.strip()

    class Config:
        """Pydantic config."""
        str_strip_whitespace = True


class SummaryUpdate(BaseModel):
    """Schema for updating summary."""
    summary_text: Optional[str] = Field(None, min_length=10, max_length=10000)
    sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0)
    dominant_sentiment: Optional[str] = None
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    processing_time_seconds: Optional[float] = Field(None, ge=0.0)

    class Config:
        """Pydantic config."""
        str_strip_whitespace = True


class SummaryResponse(BaseModel):
    """Schema for summary response."""
    id: int
    summary_id: str
    group_id: int
    period_start: datetime
    period_end: datetime
    summary_text: str
    message_count: int
    participant_count: int
    sentiment_score: Optional[float]
    dominant_sentiment: Optional[str]
    key_topics: Optional[List[str]]
    key_decisions: Optional[List[str]]
    action_items: Optional[List[str]]
    language: str
    model_used: Optional[str]
    confidence_score: Optional[float]
    is_ai_generated: bool
    processing_time_seconds: Optional[float]
    created_at: datetime
    processed_at: datetime

    class Config:
        """Pydantic config."""
        from_attributes = True


class ConversationStatistics(BaseModel):
    """Statistics about a conversation."""
    message_count: int = Field(..., ge=0)
    participant_count: int = Field(..., ge=0)
    unique_participants: List[str] = Field(default_factory=list)
    time_range: Optional[str] = None
    avg_message_length: float = Field(default=0.0, ge=0.0)
    most_active_users: List[tuple] = Field(default_factory=list)


class GroupStats(BaseModel):
    """Statistics for group activity."""
    group_id: int = Field(..., gt=0)
    group_title: str
    total_messages: int = Field(..., ge=0)
    total_participants: int = Field(..., ge=0)
    active_participants: int = Field(..., ge=0)
    date_range: Dict[str, datetime]
    # Sentiment breakdown
    sentiment_breakdown: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of messages by sentiment"
    )
    average_sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0)
    # Message activity
    messages_per_day: float = Field(..., ge=0.0)
    avg_message_length: float = Field(..., ge=0.0)
    # Top contributors
    top_contributors: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of most active participants with message counts"
    )
    # Summary statistics
    total_summaries: int = Field(default=0, ge=0)
    last_summary_at: Optional[datetime] = None
    # Time period
    analysis_period_days: int = Field(..., ge=1)

    @validator("sentiment_breakdown")
    def validate_sentiment_breakdown(cls, v):
        """Validate sentiment breakdown keys."""
        valid_sentiments = {"positive", "negative", "neutral", "conflict", "mixed"}
        for key in v.keys():
            if key not in valid_sentiments:
                raise ValueError(f"Invalid sentiment: {key}")
        return v


class ParticipantStats(BaseModel):
    """Statistics for a participant."""
    user_id: int = Field(..., gt=0)
    username: Optional[str] = None
    full_name: Optional[str] = None
    message_count: int = Field(..., ge=0)
    first_message_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    avg_message_length: float = Field(default=0.0, ge=0.0)
    sentiment_profile: Dict[str, float] = Field(
        default_factory=dict,
        description="Sentiment distribution percentages"
    )
    dominant_emotion: Optional[str] = None


class HealthCheck(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status: healthy, degraded, unhealthy")
    timestamp: datetime
    redis_connected: bool
    database_connected: bool
    uptime_seconds: Optional[float] = None
    error_message: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""
    items: List[Any]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=100)
    total_pages: int = Field(..., ge=0)

    @root_validator(skip_on_failure=True)
    def validate_pagination(cls, values):
        """Validate pagination values."""
        total = values.get("total", 0)
        page_size = values.get("page_size", 1)
        total_pages = values.get("total_pages", 0)
        expected_total_pages = (total + page_size - 1) // page_size
        if total_pages != expected_total_pages:
            values["total_pages"] = expected_total_pages
        return values


class MessageBatch(BaseModel):
    """Batch of messages for processing."""
    messages: List[MessageCreate] = Field(..., min_items=1, max_items=1000)
    group_id: int = Field(..., gt=0)

    @validator("messages")
    def validate_all_from_same_group(cls, v, values):
        """Validate all messages are from the same group."""
        group_id = values.get("group_id")
        if group_id:
            for msg in v:
                if msg.group_id != group_id:
                    raise ValueError(
                        f"All messages must be from group {group_id}, "
                        f"found message from {msg.group_id}"
                    )
        return v


class SummaryRequest(BaseModel):
    """Request for generating a summary."""
    group_id: int = Field(..., gt=0, description="Telegram group ID")
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    limit: int = Field(default=1000, ge=1, le=10000, description="Max messages to summarize")
    language: str = Field(default="en", min_length=2, max_length=10)

    @root_validator(skip_on_failure=True)
    def validate_period(cls, values):
        """Validate period if provided."""
        start = values.get("period_start")
        end = values.get("period_end")
        if start and end and start >= end:
            raise ValueError("period_start must be before period_end")
        return values


class SummaryBatchRequest(BaseModel):
    """Request for batch summary generation."""
    group_ids: List[int] = Field(..., min_items=1, max_items=100)
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None

    @validator("group_ids")
    def validate_unique_ids(cls, v):
        """Ensure group IDs are unique."""
        if len(v) != len(set(v)):
            raise ValueError("Duplicate group IDs in request")
        return v


class RateLimitInfo(BaseModel):
    """Information about rate limits."""
    limit: int = Field(..., ge=1)
    remaining: int = Field(..., ge=0)
    reset_at: datetime
    retry_after_seconds: int = Field(..., ge=1)


class ProcessingJob(BaseModel):
    """Information about a processing job."""
    job_id: str
    status: str = Field(..., description="pending, processing, completed, failed")
    progress_percent: int = Field(..., ge=0, le=100)
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


# Export all schemas
__all__ = [
    "SentimentType",
    "EmotionType",
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "GroupBase",
    "GroupCreate",
    "GroupUpdate",
    "GroupResponse",
    "MessageBase",
    "MessageCreate",
    "MessageUpdate",
    "MessageResponse",
    "SentimentAnalysis",
    "SummaryCreate",
    "SummaryUpdate",
    "SummaryResponse",
    "ConversationStatistics",
    "GroupStats",
    "ParticipantStats",
    "HealthCheck",
    "ErrorResponse",
    "PaginatedResponse",
    "MessageBatch",
    "SummaryRequest",
    "SummaryBatchRequest",
    "RateLimitInfo",
    "ProcessingJob",
]
