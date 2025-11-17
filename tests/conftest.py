"""Pytest configuration and shared fixtures for testing."""

import pytest
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
import logging

from bot.models.database import Base
from bot.utils.rate_limiter import UserRateLimiter, GroupRateLimiter, CombinedRateLimiter
from bot.utils.queue import JobQueue
from telegram.ext import Application, ContextTypes
from telegram import User, Chat, Update, Message


# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """Create test database with in-memory SQLite."""
    # Use PostgreSQL in-memory if available, otherwise SQLite
    database_url = "sqlite+aiosqlite:///:memory:"
    
    engine = create_async_engine(
        database_url,
        echo=False,
        poolclass=StaticPool,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    SessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    session = SessionLocal()
    yield session
    await session.close()
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def mock_redis() -> AsyncGenerator[AsyncMock, None]:
    """Create mock Redis client."""
    with patch("redis.asyncio.from_url") as mock:
        redis_client = AsyncMock(spec=redis.Redis)
        redis_client.get = AsyncMock(return_value=None)
        redis_client.set = AsyncMock(return_value=True)
        redis_client.incr = AsyncMock(return_value=1)
        redis_client.decr = AsyncMock(return_value=0)
        redis_client.delete = AsyncMock(return_value=1)
        redis_client.expire = AsyncMock(return_value=True)
        redis_client.lpush = AsyncMock(return_value=1)
        redis_client.rpop = AsyncMock(return_value=None)
        redis_client.llen = AsyncMock(return_value=0)
        redis_client.exists = AsyncMock(return_value=False)
        redis_client.hgetall = AsyncMock(return_value={})
        redis_client.hset = AsyncMock(return_value=1)
        redis_client.flushdb = AsyncMock(return_value=True)
        redis_client.close = AsyncMock(return_value=None)
        
        mock.return_value = redis_client
        yield redis_client


@pytest.fixture
def mock_telegram_user():
    """Create mock Telegram User."""
    return User(
        id=123456789,
        is_bot=False,
        first_name="Test",
        last_name="User",
        username="testuser",
    )


@pytest.fixture
def mock_telegram_chat():
    """Create mock Telegram Chat."""
    return Chat(
        id=-9876543210,
        type="group",
        title="Test Group",
        username="testgroup",
    )


@pytest.fixture
def mock_telegram_message(mock_telegram_user, mock_telegram_chat):
    """Create mock Telegram Message."""
    return Message(
        message_id=1,
        date=None,
        chat=mock_telegram_chat,
        from_user=mock_telegram_user,
        text="Test message",
    )


@pytest.fixture
def mock_telegram_update(mock_telegram_message):
    """Create mock Telegram Update."""
    update = MagicMock(spec=Update)
    update.update_id = 1
    update.message = mock_telegram_message
    return update


@pytest.fixture
async def mock_application() -> AsyncMock:
    """Create mock Telegram Application."""
    app = AsyncMock(spec=Application)
    app.bot = AsyncMock()
    app.bot.send_message = AsyncMock(return_value=None)
    app.bot.edit_message_text = AsyncMock(return_value=None)
    app.bot.send_chat_action = AsyncMock(return_value=None)
    app.bot.get_chat_member_count = AsyncMock(return_value=10)
    app.user_data = {}
    app.chat_data = {}
    
    context = AsyncMock(spec=ContextTypes)
    context.application = app
    context.user_data = {}
    context.chat_data = {}
    
    return app, context


@pytest.fixture
async def mock_context(mock_telegram_user, mock_telegram_chat):
    """Create mock Telegram context."""
    context = AsyncMock(spec=ContextTypes)
    context.user_data = {}
    context.chat_data = {}
    context.application = AsyncMock()
    context.application.bot = AsyncMock()
    context.application.bot.send_message = AsyncMock(return_value=None)
    context.application.bot.edit_message_text = AsyncMock(return_value=None)
    context.application.bot.send_chat_action = AsyncMock(return_value=None)
    
    return context


@pytest.fixture
async def rate_limiter(mock_redis):
    """Create CombinedRateLimiter instance."""
    limiter = CombinedRateLimiter(mock_redis)
    return limiter


@pytest.fixture
async def job_queue(mock_redis):
    """Create JobQueue instance."""
    queue = JobQueue(mock_redis)
    return queue


@pytest.fixture
def mock_deepseek_response():
    """Create mock DeepSeek API response."""
    return {
        "choices": [
            {
                "message": {
                    "content": "This is a test summary of the conversation."
                }
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
        }
    }


@pytest.fixture
def mock_deepseek_error_response():
    """Create mock DeepSeek error response."""
    return {
        "error": {
            "message": "Rate limit exceeded",
            "type": "rate_limit_error"
        }
    }


# Helper functions for tests
def create_test_message(text: str, user_id: int = 123456789, message_id: int = 1):
    """Create a test message object."""
    user = User(id=user_id, is_bot=False, first_name="Test")
    chat = Chat(id=-9876543210, type="group", title="Test Group")
    return Message(
        message_id=message_id,
        date=None,
        chat=chat,
        from_user=user,
        text=text,
    )


def create_test_update(message: Message = None, update_id: int = 1):
    """Create a test update object."""
    update = MagicMock(spec=Update)
    update.update_id = update_id
    update.message = message or create_test_message("Test message")
    return update
