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
