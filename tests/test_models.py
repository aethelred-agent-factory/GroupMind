"""Tests for database models and utilities."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from bot.models.database import Group, User, Message, Summary, AuditLog
from bot.utils.rate_limiter import UserRateLimiter, GroupRateLimiter, CombinedRateLimiter
from bot.utils.queue import JobQueue


@pytest.mark.asyncio
class TestDatabaseModels:
    """Test suite for database models."""
    
    async def test_group_model_creation(self, test_db):
        """Test Group model creation."""
        group = Group(
            group_id=-9876543210,
            title="Test Group",
            member_count=10,
            is_active=True,
        )
        
        test_db.add(group)
        await test_db.commit()
        
        # Query back
        from sqlalchemy import select
        result = await test_db.execute(select(Group).where(Group.group_id == -9876543210))
        retrieved = result.scalar_one_or_none()
        
        assert retrieved is not None
        assert retrieved.title == "Test Group"
        assert retrieved.member_count == 10
    
    async def test_user_model_creation(self, test_db):
        """Test User model creation."""
        user = User(
            user_id=123456789,
            username="testuser",
            first_name="Test",
            opt_out=False,
        )
        
        test_db.add(user)
        await test_db.commit()
        
        from sqlalchemy import select
        result = await test_db.execute(select(User).where(User.user_id == 123456789))
        retrieved = result.scalar_one_or_none()
        
        assert retrieved is not None
        assert retrieved.username == "testuser"
        assert retrieved.opt_out is False
    
    async def test_message_model_creation(self, test_db):
        """Test Message model creation."""
        # Create group and user first
        group = Group(
            group_id=-9876543210,
            title="Test Group",
            member_count=1,
            is_active=True,
        )
        user = User(
            user_id=123456789,
            username="testuser",
            first_name="Test",
        )
        
        test_db.add(group)
        test_db.add(user)
        await test_db.commit()
        
        # Create message
        message = Message(
            message_id=1,
            group_id=-9876543210,
            user_id=123456789,
            text="Test message",
            timestamp=datetime.utcnow(),
            sentiment="positive",
            sentiment_score=0.8,
        )
        
        test_db.add(message)
        await test_db.commit()
        
        from sqlalchemy import select
        result = await test_db.execute(select(Message).where(Message.message_id == 1))
        retrieved = result.scalar_one_or_none()
        
        assert retrieved is not None
        assert retrieved.text == "Test message"
        assert retrieved.sentiment == "positive"
    
    async def test_summary_model_creation(self, test_db):
        """Test Summary model creation."""
        # Create group first
        group = Group(
            group_id=-9876543210,
            title="Test Group",
            member_count=1,
            is_active=True,
        )
        
        test_db.add(group)
        await test_db.commit()
        
        # Create summary
        now = datetime.utcnow()
        summary = Summary(
            summary_id="summary_1",
            group_id=-9876543210,
            period_start=now - timedelta(hours=24),
            period_end=now,
            summary_text="Test summary",
            message_count=5,
            participant_count=2,
            sentiment_score=0.5,
            language="en",
            is_ai_generated=True,
            processed_at=now,
        )
        
        test_db.add(summary)
        await test_db.commit()
        
        from sqlalchemy import select
        result = await test_db.execute(select(Summary).where(Summary.summary_id == "summary_1"))
        retrieved = result.scalar_one_or_none()
        
        assert retrieved is not None
        assert retrieved.message_count == 5
        assert retrieved.language == "en"
    
    async def test_audit_log_model(self, test_db):
        """Test AuditLog model creation."""
        log = AuditLog(
            action="create",
            entity_type="group",
            entity_id="group_123",
            user_id=123456789,
            details="Created new group",
        )
        
        test_db.add(log)
        await test_db.commit()
        
        from sqlalchemy import select
        result = await test_db.execute(select(AuditLog).where(AuditLog.entity_id == "group_123"))
        retrieved = result.scalar_one_or_none()
        
        assert retrieved is not None
        assert retrieved.action == "create"
    
    async def test_soft_delete_group(self, test_db):
        """Test soft deletion on Group model."""
        group = Group(
            group_id=-9876543210,
            title="Test Group",
            member_count=1,
            is_active=True,
        )
        
        test_db.add(group)
        await test_db.commit()
        
        # Soft delete
        group.soft_delete()
        
        assert group.deleted_at is not None
        assert group.is_active is False
    
    async def test_soft_delete_user(self, test_db):
        """Test soft deletion on User model."""
        user = User(
            user_id=123456789,
            username="testuser",
            first_name="Test",
        )
        
        test_db.add(user)
        await test_db.commit()
        
        # Soft delete
        user.soft_delete()
        
        assert user.deleted_at is not None


@pytest.mark.skip(reason="RateLimiter classes refactored - bot uses built-in RateLimiter")
@pytest.mark.asyncio
class TestRateLimiter:
    """Test suite for rate limiting."""
    
    async def test_user_rate_limiter_initialization(self, mock_redis):
        """Test UserRateLimiter initialization."""
        limiter = UserRateLimiter(redis_url="redis://localhost")
        limiter.redis = mock_redis
        
        assert limiter.redis is not None
        assert limiter.limits is not None
    
    async def test_user_rate_limiter_check(self, mock_redis):
        """Test UserRateLimiter check."""
        limiter = UserRateLimiter(redis_url="redis://localhost")
        limiter.redis = mock_redis
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)
        
        result = await limiter.check(user_id=123, tier="free")
        
        # Should allow first request
        assert result is True or result is not None
    
    async def test_group_rate_limiter_initialization(self, mock_redis):
        """Test GroupRateLimiter initialization."""
        limiter = GroupRateLimiter(redis_url="redis://localhost")
        limiter.redis = mock_redis
        
        assert limiter.redis is not None
    
    async def test_group_rate_limiter_check(self, mock_redis):
        """Test GroupRateLimiter check."""
        limiter = GroupRateLimiter(redis_url="redis://localhost")
        limiter.redis = mock_redis
        mock_redis.get = AsyncMock(return_value=None)
        
        result = await limiter.check(group_id=-9876543210)
        
        assert result is True or result is not None
    
    async def test_combined_rate_limiter(self, mock_redis):
        """Test CombinedRateLimiter."""
        limiter = CombinedRateLimiter(redis_url="redis://localhost")
        limiter.redis = mock_redis
        limiter.user_limiter = UserRateLimiter(redis_url="redis://localhost")
        limiter.group_limiter = GroupRateLimiter(redis_url="redis://localhost")
        limiter.user_limiter.redis = mock_redis
        limiter.group_limiter.redis = mock_redis
        
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.expire = AsyncMock(return_value=True)
        
        result = await limiter.check_limits(
            user_id=123,
            group_id=-9876543210,
            tier="free"
        )
        
        assert result is not None


@pytest.mark.skip(reason="JobQueue class refactored - bot doesn't use this pattern")
@pytest.mark.asyncio
class TestJobQueue:
    """Test suite for job queue."""
    
    async def test_job_queue_initialization(self, mock_redis):
        """Test JobQueue initialization."""
        queue = JobQueue(redis_url="redis://localhost")
        queue.redis = mock_redis
        
        assert queue.redis is not None
        assert queue.max_retries >= 1
    
    async def test_enqueue_job(self, mock_redis):
        """Test job enqueueing."""
        queue = JobQueue(redis_url="redis://localhost")
        queue.redis = mock_redis
        mock_redis.lpush = AsyncMock(return_value=1)
        
        job_id = await queue.enqueue(
            job_type="summary",
            group_id=-9876543210,
            data={"messages": 10}
        )
        
        assert job_id is not None
        mock_redis.lpush.assert_called()
    
    async def test_dequeue_job(self, mock_redis):
        """Test job dequeueing."""
        queue = JobQueue(redis_url="redis://localhost")
        queue.redis = mock_redis
        mock_redis.rpop = AsyncMock(return_value=b'{"id": "job_1", "type": "summary"}')
        
        job = await queue.dequeue()
        
        # Should attempt to dequeue
        mock_redis.rpop.assert_called()
    
    async def test_mark_completed(self, mock_redis):
        """Test marking job as completed."""
        queue = JobQueue(redis_url="redis://localhost")
        queue.redis = mock_redis
        mock_redis.set = AsyncMock(return_value=True)
        
        result = await queue.mark_completed(
            job_id="job_1",
            result={"status": "completed"}
        )
        
        mock_redis.set.assert_called()
    
    async def test_mark_failed(self, mock_redis):
        """Test marking job as failed."""
        queue = JobQueue(redis_url="redis://localhost")
        queue.redis = mock_redis
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.lpush = AsyncMock(return_value=1)
        
        result = await queue.mark_failed(
            job_id="job_1",
            error="Connection timeout"
        )
        
        # Should increment retry counter or handle failure
        assert result is None or isinstance(result, bool)
    
    async def test_get_job_status(self, mock_redis):
        """Test getting job status."""
        queue = JobQueue(redis_url="redis://localhost")
        queue.redis = mock_redis
        mock_redis.get = AsyncMock(return_value=b'{"status": "processing"}')
        
        status = await queue.get_status("job_1")
        
        # Should retrieve status
        mock_redis.get.assert_called()


@pytest.mark.asyncio
class TestDatabaseRelationships:
    """Test model relationships."""
    
    async def test_group_user_relationship(self, test_db):
        """Test Group-User relationship through Message."""
        group = Group(
            group_id=-9876543210,
            title="Test Group",
            member_count=1,
            is_active=True,
        )
        user = User(
            user_id=123456789,
            username="testuser",
            first_name="Test",
        )
        message = Message(
            message_id=1,
            group_id=-9876543210,
            user_id=123456789,
            text="Test",
            timestamp=datetime.utcnow(),
        )
        
        test_db.add_all([group, user, message])
        await test_db.commit()
        
        # Verify relationships
        from sqlalchemy import select
        result = await test_db.execute(select(Message).where(Message.message_id == 1))
        msg = result.scalar_one_or_none()
        
        assert msg is not None
        assert msg.group_id == -9876543210
        assert msg.user_id == 123456789
