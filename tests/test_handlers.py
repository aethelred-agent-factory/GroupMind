"""Tests for command handlers."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from telegram import Update, User, Chat, Message
from telegram.error import TelegramError
import logging

from bot.handlers.commands import CommandHandler, RedisRateLimiter, SummaryJobQueue
from bot.utils.rate_limiter import CombinedRateLimiter, UserTier
from bot.models.schemas import GroupStats


logger = logging.getLogger(__name__)


@pytest.mark.asyncio
class TestCommandHandler:
    """Test suite for CommandHandler class."""
    
    async def test_start_command_new_user(
        self, 
        mock_context, 
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test /start command with a new user."""
        handler = CommandHandler(redis_url="redis://localhost")
        handler.redis = mock_redis
        
        # Create update using MagicMock
        update = MagicMock(spec=Update)
        update.update_id = 1
        message = Message(
            message_id=1,
            date=None,
            chat=mock_telegram_chat,
            from_user=mock_telegram_user,
            text="/start",
        )
        update.message = message
        
        # Execute command
        result = await handler.start(update, mock_context)
        
        # Assertions
        mock_context.application.bot.send_message.assert_called()
        call_args = mock_context.application.bot.send_message.call_args
        assert call_args[1]["chat_id"] == mock_telegram_chat.id
        assert "welcome" in call_args[1]["text"].lower()
    
    async def test_start_command_existing_user(
        self,
        mock_context,
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test /start command with existing user."""
        handler = CommandHandler(redis_url="redis://localhost")
        handler.redis = mock_redis
        mock_redis.get = AsyncMock(return_value=b"1")  # User exists
        
        update = MagicMock(spec=Update)
        update.update_id = 2
        message = Message(
            message_id=2,
            date=None,
            chat=mock_telegram_chat,
            from_user=mock_telegram_user,
            text="/start",
        )
        update.message = message
        
        result = await handler.start(update, mock_context)
        
        mock_context.application.bot.send_message.assert_called()
    
    async def test_help_command(self, mock_context, mock_telegram_chat, mock_redis):
        """Test /help command."""
        handler = CommandHandler(redis_url="redis://localhost")
        handler.redis = mock_redis
        
        update = MagicMock(spec=Update)
        update.update_id = 3
        user = User(id=123, is_bot=False, first_name="Test")
        message = Message(
            message_id=3,
            date=None,
            chat=mock_telegram_chat,
            from_user=user,
            text="/help",
        )
        update.message = message
        
        result = await handler.help_command(update, mock_context)
        
        mock_context.application.bot.send_message.assert_called()
        call_args = mock_context.application.bot.send_message.call_args
        assert "available commands" in call_args[1]["text"].lower() or "help" in call_args[1]["text"].lower()
    
    async def test_summary_command_not_authorized(
        self,
        mock_context,
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test /summary command without authorization."""
        handler = CommandHandler(redis_url="redis://localhost")
        handler.redis = mock_redis
        handler._check_authorization = AsyncMock(return_value=False)
        
        update = MagicMock(spec=Update)
        update.update_id = 4
        message = Message(
            message_id=4,
            date=None,
            chat=mock_telegram_chat,
            from_user=mock_telegram_user,
            text="/summary",
        )
        update.message = message
        
        result = await handler.summary(update, mock_context)
        
        # Should send unauthorized message
        mock_context.application.bot.send_message.assert_called()
        call_args = mock_context.application.bot.send_message.call_args
        assert "not authorized" in call_args[1]["text"].lower() or "permission" in call_args[1]["text"].lower()
    
    async def test_summary_command_rate_limited(
        self,
        mock_context,
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test /summary command when rate limited."""
        handler = CommandHandler(redis_url="redis://localhost")
        handler.redis = mock_redis
        handler._check_authorization = AsyncMock(return_value=True)
        handler._check_rate_limit = AsyncMock(return_value=(False, 300))  # Rate limited
        
        update = MagicMock(spec=Update)
        update.update_id = 5
        message = Message(
            message_id=5,
            date=None,
            chat=mock_telegram_chat,
            from_user=mock_telegram_user,
            text="/summary",
        )
        update.message = message
        
        result = await handler.summary(update, mock_context)
        
        # Should send rate limit message
        mock_context.application.bot.send_message.assert_called()
        call_args = mock_context.application.bot.send_message.call_args
        assert "rate limit" in call_args[1]["text"].lower() or "try again" in call_args[1]["text"].lower()
    
    async def test_summary_command_success(
        self,
        mock_context,
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test /summary command successful execution."""
        handler = CommandHandler(redis_url="redis://localhost")
        handler.redis = mock_redis
        handler._check_authorization = AsyncMock(return_value=True)
        handler._check_rate_limit = AsyncMock(return_value=(True, 0))
        handler._enqueue_summary_job = AsyncMock(return_value="job_123")
        
        update = MagicMock(spec=Update)
        update.update_id = 6
        message = Message(
            message_id=6,
            date=None,
            chat=mock_telegram_chat,
            from_user=mock_telegram_user,
            text="/summary",
        )
        
        result = await handler.summary(update, mock_context)
        
        # Should enqueue job and send processing message
        handler._enqueue_summary_job.assert_called()
        mock_context.application.bot.send_message.assert_called()


@pytest.mark.asyncio
class TestRedisRateLimiter:
    """Test suite for RedisRateLimiter class."""
    
    async def test_rate_limiter_initialization(self, mock_redis):
        """Test rate limiter initialization."""
        limiter = RedisRateLimiter(redis_url="redis://localhost")
        limiter.redis = mock_redis
        
        assert limiter.redis is not None
        assert hasattr(limiter, 'check_limit')
    
    async def test_check_limit_within_quota(self, mock_redis):
        """Test rate limit check within quota."""
        limiter = RedisRateLimiter(redis_url="redis://localhost")
        limiter.redis = mock_redis
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)
        
        # Should allow first request
        result = await limiter.check_limit("user_123", limit=5, window=60)
        
        assert result is True
        mock_redis.incr.assert_called()
    
    async def test_check_limit_exceeded(self, mock_redis):
        """Test rate limit when exceeded."""
        limiter = RedisRateLimiter(redis_url="redis://localhost")
        limiter.redis = mock_redis
        mock_redis.get = AsyncMock(return_value=b"10")  # Already at limit
        
        # Should deny request
        result = await limiter.check_limit("user_123", limit=5, window=60)
        
        assert result is False


@pytest.mark.asyncio
class TestSummaryJobQueue:
    """Test suite for SummaryJobQueue class."""
    
    async def test_enqueue_job(self, mock_redis):
        """Test job enqueueing."""
        queue = SummaryJobQueue(mock_redis)
        mock_redis.rpush = AsyncMock(return_value=1)
        
        job_id = await queue.enqueue(group_id=123, user_id=456)
        
        assert job_id is not None
        mock_redis.rpush.assert_called()
    
    async def test_dequeue_job(self, mock_redis):
        """Test job dequeueing."""
        queue = SummaryJobQueue(mock_redis)
        mock_redis.rpop = AsyncMock(return_value=b'{"group_id": "123", "message_limit": 10}')
        
        job = await queue.dequeue()
        
        # Result depends on actual implementation
        mock_redis.rpop.assert_called()
    
    async def test_mark_job_complete(self, mock_redis):
        """Test marking job as complete."""
        queue = SummaryJobQueue(mock_redis)
        mock_redis.set = AsyncMock(return_value=True)
        
        result = await queue.mark_completed("job_123", {"status": "completed"})
        
        mock_redis.set.assert_called()
    
    async def test_mark_job_failed(self, mock_redis):
        """Test marking job as failed."""
        queue = SummaryJobQueue(mock_redis)
        mock_redis.set = AsyncMock(return_value=True)
        
        result = await queue.mark_failed("job_123", "Error message")
        
        mock_redis.set.assert_called()


@pytest.mark.asyncio
class TestCommandHandlerErrors:
    """Test error handling in command handlers."""
    
    async def test_start_command_telegram_error(
        self,
        mock_context,
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test /start command with Telegram API error."""
        handler = CommandHandler(redis_url="redis://localhost")
        handler.redis = mock_redis
        
        # Simulate Telegram error
        mock_context.application.bot.send_message = AsyncMock(
            side_effect=TelegramError("Connection error")
        )
        
        update = MagicMock(spec=Update)
        update.update_id = 7
        message = Message(
            message_id=7,
            date=None,
            chat=mock_telegram_chat,
            from_user=mock_telegram_user,
            text="/start",
        )
        update.message = message
        
        # Should handle error gracefully
        with pytest.raises(TelegramError):
            await handler.start(update, mock_context)
    
    async def test_summary_command_redis_error(
        self,
        mock_context,
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test /summary command with Redis error."""
        handler = CommandHandler(redis_url="redis://localhost")
        handler._check_authorization = AsyncMock(return_value=True)
        handler._check_rate_limit = AsyncMock(side_effect=Exception("Redis error"))
        
        update = MagicMock(spec=Update)
        update.update_id = 8
        message = Message(
            message_id=8,
            date=None,
            chat=mock_telegram_chat,
            from_user=mock_telegram_user,
            text="/summary",
        )
        
        # Should handle error
        with pytest.raises(Exception):
            await handler.summary(update, mock_context)


@pytest.mark.asyncio
class TestAuthorizationChecks:
    """Test authorization logic."""
    
    async def test_admin_authorization(self, mock_redis):
        """Test admin user authorization."""
        handler = CommandHandler(redis_url="redis://localhost")
        handler.redis = mock_redis
        
        # Mock admin list
        mock_redis.sismember = AsyncMock(return_value=True)
        
        result = await handler._check_authorization(123, -9876543210)
        
        # Should be authorized
        assert result is True
    
    async def test_non_admin_authorization(self, mock_redis):
        """Test non-admin user authorization."""
        handler = CommandHandler(redis_url="redis://localhost")
        handler.redis = mock_redis
        
        # Mock non-admin
        mock_redis.sismember = AsyncMock(return_value=False)
        
        result = await handler._check_authorization(456, -9876543210)
        
        # Should not be authorized
        assert result is False
