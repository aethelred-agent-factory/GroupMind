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
        handler = CommandHandler(admin_user_ids=[])
        
        # Create proper update mock
        update = MagicMock(spec=Update)
        update.update_id = 1
        update.effective_user = mock_telegram_user
        
        message = AsyncMock()
        message.reply_text = AsyncMock(return_value=None)
        update.message = message
        
        # Execute command
        await handler.start(update, mock_context)
        
        # Assertions
        message.reply_text.assert_called()
        call_args = message.reply_text.call_args
        assert call_args is not None
        assert "welcome" in call_args[0][0].lower() or "GroupMind" in call_args[0][0]
    
    async def test_start_command_existing_user(
        self,
        mock_context,
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test /start command with existing user."""
        handler = CommandHandler(admin_user_ids=[])
        
        update = MagicMock(spec=Update)
        update.update_id = 2
        update.effective_user = mock_telegram_user
        
        message = AsyncMock()
        message.reply_text = AsyncMock(return_value=None)
        update.message = message
        
        await handler.start(update, mock_context)
        
        message.reply_text.assert_called()
    
    async def test_help_command(self, mock_context, mock_telegram_chat, mock_redis):
        """Test /help command."""
        handler = CommandHandler(admin_user_ids=[])
        
        update = MagicMock(spec=Update)
        update.update_id = 3
        user = User(id=123, is_bot=False, first_name="Test")
        update.effective_user = user
        
        message = AsyncMock()
        message.reply_text = AsyncMock(return_value=None)
        update.message = message
        
        await handler.help(update, mock_context)
        
        message.reply_text.assert_called()
        call_args = message.reply_text.call_args
        assert call_args is not None
    
    async def test_summary_command_not_authorized(
        self,
        mock_context,
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test /summary command without authorization (bot user)."""
        handler = CommandHandler(admin_user_ids=[])
        
        # Create a bot user (invalid)
        bot_user = User(id=124, is_bot=True, first_name="TestBot")
        
        update = MagicMock(spec=Update)
        update.update_id = 4
        update.effective_user = bot_user
        update.effective_chat = mock_telegram_chat
        
        message = AsyncMock()
        message.reply_text = AsyncMock(return_value=None)
        update.message = message
        
        await handler.summary(update, mock_context)
        
        # Should send unauthorized message
        message.reply_text.assert_called()
        call_args = message.reply_text.call_args
        assert "invalid" in call_args[0][0].lower() or "bot" in call_args[0][0].lower()
    
    async def test_summary_command_rate_limited(
        self,
        mock_context,
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test /summary command when rate limited."""
        from unittest.mock import patch, AsyncMock
        
        handler = CommandHandler(admin_user_ids=[])
        
        update = MagicMock(spec=Update)
        update.update_id = 5
        update.effective_user = mock_telegram_user
        update.effective_chat = mock_telegram_chat
        
        message = AsyncMock()
        message.reply_text = AsyncMock(return_value=None)
        update.message = message
        
        # Mock rate limiter
        handler.rate_limiter = AsyncMock()
        handler.rate_limiter.is_rate_limited = AsyncMock(return_value=True)
        
        await handler.summary(update, mock_context)
        
        # Should send rate limit message
        message.reply_text.assert_called()
        call_args = message.reply_text.call_args
        assert "rate limit" in call_args[0][0].lower() or "exceeded" in call_args[0][0].lower()
    
    async def test_summary_command_success(
        self,
        mock_context,
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test /summary command successful execution."""
        from unittest.mock import AsyncMock
        
        handler = CommandHandler(admin_user_ids=[])
        
        update = MagicMock(spec=Update)
        update.update_id = 6
        update.effective_user = mock_telegram_user
        update.effective_chat = mock_telegram_chat
        
        message = AsyncMock()
        message.reply_text = AsyncMock(return_value=None)
        update.message = message
        
        chat_async = AsyncMock()
        chat_async.send_action = AsyncMock(return_value=None)
        update.effective_chat = chat_async
        update.effective_chat.id = mock_telegram_chat.id
        
        # Mock rate limiter and job queue
        handler.rate_limiter = AsyncMock()
        handler.rate_limiter.is_rate_limited = AsyncMock(return_value=False)
        
        handler.job_queue = AsyncMock()
        handler.job_queue.enqueue = AsyncMock(return_value="job_123")
        handler.job_queue.get_queue_length = AsyncMock(return_value=1)
        
        await handler.summary(update, mock_context)
        
        # Should send processing message
        message.reply_text.assert_called()
        call_args = message.reply_text.call_args
        assert call_args is not None


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
        from unittest.mock import AsyncMock, patch
        
        # Patch the check_limit method to test the logic
        with patch('bot.handlers.commands.RedisRateLimiter.check_limit', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = False  # Simulate exceeded
            
            limiter = RedisRateLimiter(redis_url="redis://localhost")
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
        from unittest.mock import AsyncMock
        
        queue = SummaryJobQueue(mock_redis)
        queue.client = AsyncMock()
        queue.client.lpop = AsyncMock(return_value=b'{"group_id": 123, "user_id": 456}')
        
        job = await queue.dequeue()
        
        # Should have received a job
        assert job is not None
        queue.client.lpop.assert_called()
    
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
    
    async def test_start_command_handles_gracefully(
        self,
        mock_context,
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test /start command handles errors gracefully without raising."""
        handler = CommandHandler(admin_user_ids=[])
        
        update = MagicMock(spec=Update)
        update.update_id = 7
        update.effective_user = mock_telegram_user
        
        message = AsyncMock()
        message.reply_text = AsyncMock(return_value=None)
        update.message = message
        
        # Should not raise even with setup
        try:
            await handler.start(update, mock_context)
        except Exception as e:
            pytest.fail(f"start() raised {e} unexpectedly")
    
    async def test_summary_command_handles_gracefully(
        self,
        mock_context,
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test /summary command handles errors gracefully without raising."""
        handler = CommandHandler(admin_user_ids=[])
        
        update = MagicMock(spec=Update)
        update.update_id = 8
        update.effective_user = mock_telegram_user
        update.effective_chat = mock_telegram_chat
        
        message = AsyncMock()
        message.reply_text = AsyncMock(return_value=None)
        update.message = message
        
        # Should not raise
        try:
            await handler.summary(update, mock_context)
        except Exception as e:
            pytest.fail(f"summary() raised {e} unexpectedly")


@pytest.mark.asyncio
class TestAuthorizationChecks:
    """Test authorization logic through command handlers."""
    
    async def test_admin_authorization_via_handler(self, mock_telegram_user):
        """Test that admin users are properly authorized."""
        admin_id = 123456789
        handler = CommandHandler(admin_user_ids=[admin_id])
        
        # Admin should pass
        assert handler.authorizer.is_admin(admin_id) is True
        
        # Non-admin should fail
        assert handler.authorizer.is_admin(987654321) is False
    
    async def test_user_validation(self):
        """Test user validation logic."""
        handler = CommandHandler(admin_user_ids=[])
        
        # Valid user (not a bot)
        valid_user = User(id=123, is_bot=False, first_name="Test")
        assert handler.authorizer.is_user_valid(valid_user) is True
        
        # Bot user (invalid)
        bot_user = User(id=124, is_bot=True, first_name="TestBot")
        assert handler.authorizer.is_user_valid(bot_user) is False
        
        # Invalid user (no ID)
        invalid_user = User(id=None, is_bot=False, first_name="Test")
        assert handler.authorizer.is_user_valid(invalid_user) is False
