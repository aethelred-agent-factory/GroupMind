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

# Import models and services
from bot.models.database import Group, User, Message as DBMessage, Summary
from bot.services.deepseek import DeepSeekClient, Message as APIMessage, TokenCounter
from bot.services.sentiment import SentimentAnalyzer
from sqlalchemy import select, desc, func

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
        self.application.add_handler(CommandHandler("trending", self.trending_command))
        self.application.add_handler(CommandHandler("sentiment", self.sentiment_command))
        self.application.add_handler(CommandHandler("actions", self.actions_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
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
                "<code>/summary</code> - Get a summary of recent group discussions\n"
                "<code>/trending</code> - Show trending topics from last 24h\n"
                "<code>/sentiment</code> - Analyze group sentiment and mood\n"
                "<code>/actions</code> - Extract action items from conversations\n"
                "<code>/stats</code> - View group statistics\n"
                "<code>/help</code> - Show this help message\n\n"
                "<b>How to use:</b>\n"
                "Add me to your group and I'll automatically monitor conversations. "
                "Use any command in the group to get insights!"
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

    async def trending_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /trending command - show most discussed topics.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        try:
            if not update.effective_user or not update.effective_chat:
                logger.warning("Trending command received with missing info")
                return

            chat_id = update.effective_chat.id
            await update.effective_chat.send_action("typing")

            async with self.db_manager.get_session() as session:
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                stmt = (
                    select(DBMessage.text)
                    .where(
                        (DBMessage.group_id == chat_id)
                        & (DBMessage.timestamp >= cutoff_time)
                    )
                    .limit(100)
                )
                result = await session.execute(stmt)
                messages = result.scalars().all()

                if not messages:
                    await update.message.reply_text("📊 No messages found in the past 24 hours.")
                    return

                # Extract keywords from messages
                text = " ".join(messages).lower()
                # Simple word frequency (could be enhanced with NLP)
                words = text.split()
                common_words = [
                    "is", "the", "a", "and", "or", "but", "in", "on", "at", "to", 
                    "of", "for", "with", "from", "by", "it", "that", "this", "are"
                ]
                word_freq = {}
                for word in words:
                    if len(word) > 4 and word not in common_words:
                        word_freq[word] = word_freq.get(word, 0) + 1

                top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]

                if top_words:
                    trending_text = "🔥 <b>Trending Topics (24h)</b>\n\n"
                    for i, (word, count) in enumerate(top_words, 1):
                        trending_text += f"{i}. <code>{word}</code> - mentioned {count}x\n"
                else:
                    trending_text = "📊 No trending topics found."

                await update.message.reply_text(trending_text, parse_mode="HTML")
                logger.info(f"Trending command executed in chat {chat_id}")

        except Exception as e:
            logger.error(f"Error in trending command: {e}")
            try:
                await update.message.reply_text("Sorry, couldn't fetch trending topics.")
            except Exception:
                pass

    async def sentiment_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /sentiment command - analyze group mood.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        try:
            if not update.effective_user or not update.effective_chat:
                logger.warning("Sentiment command received with missing info")
                return

            chat_id = update.effective_chat.id
            await update.effective_chat.send_action("typing")

            async with self.db_manager.get_session() as session:
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                stmt = (
                    select(DBMessage)
                    .where(
                        (DBMessage.group_id == chat_id)
                        & (DBMessage.timestamp >= cutoff_time)
                    )
                )
                result = await session.execute(stmt)
                messages = result.scalars().all()

                if not messages:
                    await update.message.reply_text("📊 No messages found.")
                    return

                # Count sentiments
                positive = sum(1 for m in messages if m.sentiment == "positive")
                negative = sum(1 for m in messages if m.sentiment == "negative")
                neutral = sum(1 for m in messages if m.sentiment == "neutral")
                total = len(messages)

                sentiment_text = "💭 <b>Group Sentiment (24h)</b>\n\n"
                sentiment_text += f"😊 Positive: {positive}/{total} ({100*positive//total}%)\n"
                sentiment_text += f"😐 Neutral: {neutral}/{total} ({100*neutral//total}%)\n"
                sentiment_text += f"😞 Negative: {negative}/{total} ({100*negative//total}%)\n"

                overall = "positive" if positive > negative else ("negative" if negative > positive else "neutral")
                emoji = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}[overall]
                sentiment_text += f"\n{emoji} <b>Overall: {overall.title()}</b>"

                await update.message.reply_text(sentiment_text, parse_mode="HTML")
                logger.info(f"Sentiment command executed in chat {chat_id}")

        except Exception as e:
            logger.error(f"Error in sentiment command: {e}")
            try:
                await update.message.reply_text("Sorry, couldn't analyze sentiment.")
            except Exception:
                pass

    async def actions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /actions command - extract action items from recent messages.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        try:
            if not update.effective_user or not update.effective_chat:
                logger.warning("Actions command received with missing info")
                return

            chat_id = update.effective_chat.id
            await update.effective_chat.send_action("typing")

            async with self.db_manager.get_session() as session:
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                stmt = (
                    select(DBMessage)
                    .where(
                        (DBMessage.group_id == chat_id)
                        & (DBMessage.timestamp >= cutoff_time)
                    )
                )
                result = await session.execute(stmt)
                messages = result.scalars().all()

                if not messages:
                    await update.message.reply_text("📊 No messages found.")
                    return

                # Find messages with action keywords
                action_keywords = ["todo", "need to", "should", "will do", "must", "have to", "i'll", "we'll", "action item", "task"]
                action_messages = []

                for msg in messages:
                    text_lower = msg.text.lower() if msg.text else ""
                    if any(keyword in text_lower for keyword in action_keywords):
                        action_messages.append((msg.text, msg.timestamp))

                if not action_messages:
                    await update.message.reply_text("✅ No pending action items found!")
                    return

                actions_text = f"✅ <b>Action Items ({len(action_messages)} found)</b>\n\n"
                for i, (text, timestamp) in enumerate(action_messages[:10], 1):
                    # Truncate long messages
                    display_text = text[:60] + "..." if len(text) > 60 else text
                    actions_text += f"{i}. <code>{display_text}</code>\n"

                await update.message.reply_text(actions_text, parse_mode="HTML")
                logger.info(f"Actions command executed in chat {chat_id}")

        except Exception as e:
            logger.error(f"Error in actions command: {e}")
            try:
                await update.message.reply_text("Sorry, couldn't extract action items.")
            except Exception:
                pass

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /stats command - show group statistics.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        try:
            if not update.effective_user or not update.effective_chat:
                logger.warning("Stats command received with missing info")
                return

            chat_id = update.effective_chat.id
            await update.effective_chat.send_action("typing")

            async with self.db_manager.get_session() as session:
                # Get group info
                group_stmt = select(Group).where(Group.group_id == chat_id)
                group_result = await session.execute(group_stmt)
                group = group_result.scalar_one_or_none()

                # Get stats for past 24 hours
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                msg_stmt = (
                    select(func.count(DBMessage.id))
                    .where(
                        (DBMessage.group_id == chat_id)
                        & (DBMessage.timestamp >= cutoff_time)
                    )
                )
                msg_result = await session.execute(msg_stmt)
                message_count = msg_result.scalar() or 0

                # Get unique users
                user_stmt = (
                    select(func.count(func.distinct(DBMessage.user_id)))
                    .where(
                        (DBMessage.group_id == chat_id)
                        & (DBMessage.timestamp >= cutoff_time)
                    )
                )
                user_result = await session.execute(user_stmt)
                unique_users = user_result.scalar() or 0

                stats_text = "📈 <b>Group Statistics (24h)</b>\n\n"
                stats_text += f"💬 Messages: {message_count}\n"
                stats_text += f"👥 Unique Users: {unique_users}\n"
                if group:
                    stats_text += f"📅 Group Created: {group.created_at.strftime('%Y-%m-%d') if group.created_at else 'Unknown'}\n"
                stats_text += f"⏱️ Last Updated: Just now"

                await update.message.reply_text(stats_text, parse_mode="HTML")
                logger.info(f"Stats command executed in chat {chat_id}")

        except Exception as e:
            logger.error(f"Error in stats command: {e}")
            try:
                await update.message.reply_text("Sorry, couldn't fetch statistics.")
            except Exception:
                pass

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
