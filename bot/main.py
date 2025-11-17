"""
GroupMind Telegram Bot - Main entry point with command handlers and message processing.

This module sets up the Telegram bot with:
- Command handlers for /start, /summary, /help
- Message handler for group messages with rate limiting
- Database session management
- Comprehensive error handling
- Async/await patterns throughout
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict
from collections import defaultdict
from contextlib import asynccontextmanager

from telegram import Update, Chat, Message
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    ContextTypes,
    ApplicationBuilder,
    CommandHandler,
)
from telegram.error import TelegramError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiting middleware to prevent spam and abuse."""

    def __init__(
        self,
        max_messages_per_minute: int = 10,
        max_messages_per_hour: int = 100,
    ):
        """
        Initialize rate limiter.

        Args:
            max_messages_per_minute: Maximum messages per minute per user
            max_messages_per_hour: Maximum messages per hour per user
        """
        self.max_per_minute = max_messages_per_minute
        self.max_per_hour = max_messages_per_hour
        self.user_messages: Dict[int, list] = defaultdict(list)

    def is_rate_limited(self, user_id: int) -> bool:
        """
        Check if a user is rate limited.

        Args:
            user_id: Telegram user ID

        Returns:
            True if user is rate limited, False otherwise
        """
        now = datetime.now()
        one_minute_ago = now - timedelta(minutes=1)
        one_hour_ago = now - timedelta(hours=1)

        # Clean old entries
        self.user_messages[user_id] = [
            msg_time for msg_time in self.user_messages[user_id]
            if msg_time > one_hour_ago
        ]

        # Check limits
        recent_messages = [
            msg_time for msg_time in self.user_messages[user_id]
            if msg_time > one_minute_ago
        ]

        if len(recent_messages) >= self.max_per_minute:
            logger.warning(
                f"User {user_id} rate limited - exceeded per-minute limit"
            )
            return True

        if len(self.user_messages[user_id]) >= self.max_per_hour:
            logger.warning(
                f"User {user_id} rate limited - exceeded per-hour limit"
            )
            return True

        # Record this message
        self.user_messages[user_id].append(now)
        return False


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self, database_url: str):
        """
        Initialize database manager.

        Args:
            database_url: SQLAlchemy async database URL
        """
        self.database_url = database_url
        self.engine = None
        self.async_session_maker = None

    async def initialize(self) -> None:
        """Initialize async database engine and session maker."""
        try:
            self.engine = create_async_engine(
                self.database_url,
                echo=False,
                pool_pre_ping=True,
                pool_size=20,
                max_overflow=10,
            )
            self.async_session_maker = sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    @asynccontextmanager
    async def get_session(self):
        """
        Context manager for database sessions.

        Yields:
            AsyncSession: Database session

        Raises:
            RuntimeError: If session maker not initialized
        """
        if not self.async_session_maker:
            raise RuntimeError("Database not initialized")

        session = self.async_session_maker()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()

    async def close(self) -> None:
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")


class BotManager:
    """Manages Telegram bot operations and handlers."""

    def __init__(
        self,
        token: str,
        database_url: str,
        max_messages_per_minute: int = 10,
        max_messages_per_hour: int = 100,
    ):
        """
        Initialize bot manager.

        Args:
            token: Telegram bot token
            database_url: SQLAlchemy async database URL
            max_messages_per_minute: Rate limit per minute
            max_messages_per_hour: Rate limit per hour
        """
        self.token = token
        self.application = None
        self.db_manager = DatabaseManager(database_url)
        self.rate_limiter = RateLimiter(
            max_messages_per_minute=max_messages_per_minute,
            max_messages_per_hour=max_messages_per_hour,
        )

    async def initialize(self) -> None:
        """Initialize bot application and database."""
        try:
            # Initialize database
            await self.db_manager.initialize()

            # Build Telegram application
            self.application = (
                ApplicationBuilder()
                .token(self.token)
                .build()
            )

            # Add handlers
            await self._setup_handlers()

            logger.info("Bot initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            raise

    async def _setup_handlers(self) -> None:
        """Set up command and message handlers."""
        if not self.application:
            raise RuntimeError("Application not initialized")

        # Add handlers using the correct API
        from telegram.ext import CommandHandler, MessageHandler

        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("summary", self.summary_command))
        self.application.add_handler(CommandHandler("help", self.help_command))

        # Message handler for group messages
        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUP,
                self.handle_group_message,
            )
        )

        # Error handler
        self.application.add_error_handler(self.error_handler)

        logger.info("Handlers registered successfully")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /start command.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        try:
            if not update.effective_user:
                logger.warning("Start command received without user info")
                return

            user_id = update.effective_user.id
            logger.info(f"User {user_id} started the bot")

            welcome_message = (
                "👋 Welcome to GroupMind!\n\n"
                "I'm your intelligent group chat assistant. I'll help you:\n"
                "📊 Summarize conversations\n"
                "🧠 Generate insights from group discussions\n"
                "⚡ Answer questions about recent chat topics\n\n"
                "Use /help for available commands."
            )

            await update.message.reply_text(
                welcome_message,
                parse_mode="HTML",
            )
            logger.info(f"Start message sent to user {user_id}")

        except TelegramError as e:
            logger.error(f"Telegram error in start command: {e}")
            try:
                await update.message.reply_text(
                    "Sorry, I encountered an error. Please try again later."
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Unexpected error in start command: {e}")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /help command.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        try:
            if not update.effective_user:
                logger.warning("Help command received without user info")
                return

            user_id = update.effective_user.id
            logger.info(f"User {user_id} requested help")

            help_message = (
                "<b>Available Commands:</b>\n\n"
                "<code>/start</code> - Welcome message\n"
                "<code>/help</code> - Show this help message\n"
                "<code>/summary</code> - Get a summary of recent group discussions\n\n"
                "<b>How to use:</b>\n"
                "Add me to your group and I'll automatically monitor conversations. "
                "Use /summary in the group to get insights from recent messages."
            )

            await update.message.reply_text(
                help_message,
                parse_mode="HTML",
            )
            logger.info(f"Help message sent to user {user_id}")

        except TelegramError as e:
            logger.error(f"Telegram error in help command: {e}")
            try:
                await update.message.reply_text(
                    "Sorry, I encountered an error. Please try again later."
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Unexpected error in help command: {e}")

    async def summary_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /summary command.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        try:
            if not update.effective_user or not update.effective_chat:
                logger.warning("Summary command received with missing user/chat info")
                return

            user_id = update.effective_user.id
            chat_id = update.effective_chat.id

            logger.info(f"User {user_id} requested summary in chat {chat_id}")

            # Show typing indicator
            await update.effective_chat.send_action("typing")

            # Check rate limit
            if self.rate_limiter.is_rate_limited(user_id):
                await update.message.reply_text(
                    "⏱️ You've sent too many requests. Please wait a moment before trying again."
                )
                return

            # Get recent messages from database
            try:
                from bot.models.database import Message as DBMessage
                from sqlalchemy import select, desc
                from datetime import timedelta
                
                async with self.db_manager.get_session() as session:
                    # Get last 50 messages from past 24 hours
                    cutoff_time = datetime.utcnow() - timedelta(hours=24)
                    stmt = (
                        select(DBMessage)
                        .where(
                            (DBMessage.group_id == chat_id)
                            & (DBMessage.timestamp >= cutoff_time)
                        )
                        .order_by(desc(DBMessage.timestamp))
                        .limit(50)
                    )
                    result = await session.execute(stmt)
                    messages = result.scalars().all()
                    
                    if not messages:
                        await update.message.reply_text(
                            "📊 No recent messages found in this group."
                        )
                        return
                    
                    # Generate summary using DeepSeek
                    from bot.services.deepseek import DeepSeekClient, Message as APIMessage
                    
                    api_key = os.getenv("DEEPSEEK_API_KEY")
                    if not api_key:
                        await update.message.reply_text(
                            "⚠️ AI service not configured. Please contact admin."
                        )
                        return
                    
                    client = DeepSeekClient(api_key=api_key)
                    await client.initialize()
                    
                    # Convert messages to API format
                    api_messages = [
                        APIMessage(user=str(m.user_id), text=m.text)
                        for m in reversed(messages)
                    ]
                    
                    # Get summary from AI
                    try:
                        summary_result = await client.summarize_messages(api_messages)
                        if summary_result:
                            summary_text = summary_result.summary
                        else:
                            summary_text = f"Found {len(messages)} messages. AI summarization unavailable."
                    except Exception as e:
                        logger.error(f"Error generating AI summary: {e}")
                        summary_text = f"Found {len(messages)} messages. AI summarization unavailable."
                    finally:
                        await client.close()
                    
                    summary_response = (
                        "📊 <b>Group Summary</b>\n\n"
                        f"{summary_text}"
                    )
                    
                    await update.message.reply_text(
                        summary_response,
                        parse_mode="HTML",
                    )
                    logger.info(f"Summary sent for group {chat_id}")
                    
            except Exception as e:
                logger.error(f"Database error while processing summary: {e}")
                await update.message.reply_text(
                    "Sorry, I encountered an error processing your request."
                )

        except TelegramError as e:
            logger.error(f"Telegram error in summary command: {e}")
            try:
                await update.message.reply_text(
                    "Sorry, I encountered an error. Please try again later."
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Unexpected error in summary command: {e}")

    async def handle_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle messages in group chats.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        try:
            if not update.message or not update.effective_user or not update.effective_chat:
                logger.warning("Group message received with missing information")
                return

            user_id = update.effective_user.id
            chat_id = update.effective_chat.id
            message_text = update.message.text or ""

            logger.info(
                f"Group message from user {user_id} in chat {chat_id}: "
                f"{message_text[:50]}..."
            )

            # Check rate limit
            if self.rate_limiter.is_rate_limited(user_id):
                logger.warning(f"User {user_id} rate limited in group {chat_id}")
                return

            # Store message in database
            try:
                from bot.models.database import Group, User, Message
                from sqlalchemy import select
                
                async with self.db_manager.get_session() as session:
                    # Get or create group
                    stmt = select(Group).where(Group.group_id == chat_id)
                    result = await session.execute(stmt)
                    group = result.scalar_one_or_none()
                    if not group:
                        group = Group(
                            group_id=chat_id,
                            title=update.effective_chat.title or f"Group {chat_id}",
                            bot_added_at=datetime.utcnow(),
                        )
                        session.add(group)
                        logger.info(f"Created new group {chat_id}")

                    # Get or create user
                    stmt = select(User).where(User.user_id == user_id)
                    result = await session.execute(stmt)
                    user = result.scalar_one_or_none()
                    if not user:
                        user = User(
                            user_id=user_id,
                            username=update.effective_user.username,
                            first_name=update.effective_user.first_name,
                            last_name=update.effective_user.last_name,
                        )
                        session.add(user)
                        logger.info(f"Created new user {user_id}")

                    # Store message
                    message = Message(
                        message_id=update.message.message_id,
                        group_id=chat_id,
                        user_id=user_id,
                        text=message_text,
                        timestamp=datetime.utcfromtimestamp(
                            update.message.date.timestamp()
                        ),
                    )
                    session.add(message)
                    logger.info(f"Stored message {update.message.message_id} from {user_id}")

            except Exception as e:
                logger.error(f"Database error while storing message: {e}")

        except TelegramError as e:
            logger.error(f"Telegram error handling group message: {e}")
        except Exception as e:
            logger.error(f"Unexpected error handling group message: {e}")

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle errors from Telegram.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        logger.error(f"Update {update} caused error: {context.error}")

        if update and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "An unexpected error occurred. Please try again later or contact support."
                )
            except Exception as e:
                logger.error(f"Failed to send error message: {e}")

    async def start(self) -> None:
        """Start the bot application."""
        try:
            await self.initialize()
            logger.info("Starting bot application")
            await self.application.run_polling(allowed_updates=Update.ALL_TYPES)
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise

    async def stop(self) -> None:
        """Stop the bot application."""
        try:
            if self.application:
                await self.application.stop()
            await self.db_manager.close()
            logger.info("Bot stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")


async def main() -> None:
    """Main entry point for the bot."""
    try:
        # Load configuration from environment
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable not set")

        # Create and start bot manager
        bot_manager = BotManager(
            token=token,
            database_url=database_url,
            max_messages_per_minute=10,
            max_messages_per_hour=100,
        )

        logger.info("GroupMind Bot starting up")
        await bot_manager.start()

    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    import asyncio
    
    bot_manager = BotManager(
        token=os.getenv("TELEGRAM_BOT_TOKEN"),
        database_url=os.getenv("DATABASE_URL"),
        max_messages_per_minute=10,
        max_messages_per_hour=100,
    )
    
    async def initialize_and_run():
        try:
            await bot_manager.initialize()
            logger.info("GroupMind Bot starting up")
        except Exception as e:
            logger.error(f"Fatal error during initialization: {e}")
            raise
    
    try:
        # First initialize the bot manager
        asyncio.run(initialize_and_run())
        # Then run polling (which manages its own event loop)
        bot_manager.application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
