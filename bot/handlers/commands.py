"""
Command handlers for Telegram bot.

This module provides handlers for:
- /start: Welcome message and bot capabilities
- /summary: Queue summary job with Redis rate limiting
- /help: Usage instructions and privacy notice
- Error handling for invalid commands
- User/group authorization checks
- Rate limiting per group using Redis
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import redis
import redis.asyncio as aioredis
from telegram import Update, Chat, User
from telegram.ext import ContextTypes
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


class CommandAuthorizer:
    """Handles user and group authorization for commands."""

    def __init__(self, admin_user_ids: Optional[list[int]] = None):
        """
        Initialize authorizer.

        Args:
            admin_user_ids: List of admin user IDs with full access
        """
        self.admin_user_ids = admin_user_ids or []

    def is_admin(self, user_id: int) -> bool:
        """
        Check if user is admin.

        Args:
            user_id: Telegram user ID

        Returns:
            True if user is admin, False otherwise
        """
        return user_id in self.admin_user_ids

    def is_group_valid(self, chat: Chat) -> bool:
        """
        Validate group chat.

        Args:
            chat: Telegram chat object

        Returns:
            True if group is valid, False otherwise
        """
        # Check if chat is a group
        if chat.type not in [Chat.SUPERGROUP, Chat.GROUP]:
            logger.warning(f"Invalid chat type: {chat.type}")
            return False

        # Check if bot has required permissions
        if not chat.id:
            logger.warning("Chat has no ID")
            return False

        return True

    def is_user_valid(self, user: User) -> bool:
        """
        Validate user.

        Args:
            user: Telegram user object

        Returns:
            True if user is valid, False otherwise
        """
        if not user or not user.id:
            logger.warning("Invalid user object")
            return False

        if user.is_bot:
            logger.warning(f"Bot user detected: {user.id}")
            return False

        return True


class RedisRateLimiter:
    """Rate limiting using Redis for distributed systems."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        default_limit_per_group: int = 10,
        window_seconds: int = 3600,
    ):
        """
        Initialize Redis rate limiter.

        Args:
            redis_url: Redis connection URL
            default_limit_per_group: Default rate limit per group per window
            window_seconds: Time window for rate limiting (default 1 hour)
        """
        self.redis_url = redis_url
        self.default_limit = default_limit_per_group
        self.window = window_seconds
        self.client: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        """Establish Redis connection."""
        try:
            self.client = await aioredis.from_url(
                self.redis_url,
                encoding="utf8",
                decode_responses=True,
            )
            # Test connection
            await self.client.ping()
            logger.info("Connected to Redis successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self.client:
            await self.client.close()
            logger.info("Redis connection closed")

    async def is_rate_limited(
        self,
        group_id: int,
        command: str,
        user_id: int,
    ) -> bool:
        """
        Check if user is rate limited in group for a command.

        Args:
            group_id: Telegram group ID
            command: Command name (e.g., 'summary')
            user_id: Telegram user ID

        Returns:
            True if rate limited, False otherwise
        """
        if not self.client:
            logger.warning("Redis client not initialized")
            return False

        try:
            key = f"rate_limit:{command}:group:{group_id}:user:{user_id}"

            # Get current count
            current = await self.client.incr(key)

            # Set expiration on first increment
            if current == 1:
                await self.client.expire(key, self.window)

            # Check if exceeded limit
            if current > self.default_limit:
                logger.warning(
                    f"User {user_id} rate limited in group {group_id} for /{command}"
                )
                return True

            logger.debug(
                f"User {user_id} in group {group_id}: {current}/{self.default_limit} requests"
            )
            return False

        except Exception as e:
            logger.error(f"Redis rate limit check failed: {e}")
            # Fail open - don't rate limit on error
            return False

    async def check_limit(
        self,
        key: str,
        limit: int,
        window: int,
    ) -> bool:
        """
        Check if a key is within its rate limit.

        Args:
            key: Rate limit key
            limit: Maximum count allowed
            window: Time window in seconds

        Returns:
            True if within limit, False if exceeded
        """
        if not self.redis:
            # Fallback to using client if redis not directly available
            if not self.client:
                return True

            try:
                current = await self.client.incr(key)
                if current == 1:
                    await self.client.expire(key, window)
                return current <= limit
            except Exception:
                return True

        try:
            current = await self.redis.incr(key)
            if current == 1:
                await self.redis.expire(key, window)
            return current <= limit
        except Exception:
            return True

    async def get_reset_time(
        self,
        group_id: int,
        command: str,
        user_id: int,
    ) -> Optional[int]:
        """
        Get seconds until rate limit resets.

        Args:
            group_id: Telegram group ID
            command: Command name
            user_id: Telegram user ID

        Returns:
            Seconds until reset, or None if not rate limited
        """
        if not self.client:
            return None

        try:
            key = f"rate_limit:{command}:group:{group_id}:user:{user_id}"
            ttl = await self.client.ttl(key)

            # TTL returns -1 if key exists but no expiration, -2 if key doesn't exist
            if ttl > 0:
                return ttl
            return None

        except Exception as e:
            logger.error(f"Failed to get reset time: {e}")
            return None

    async def get_group_stats(self, group_id: int) -> Dict[str, Any]:
        """
        Get rate limit statistics for a group.

        Args:
            group_id: Telegram group ID

        Returns:
            Dictionary with rate limit statistics
        """
        if not self.client:
            return {}

        try:
            pattern = f"rate_limit:*:group:{group_id}:*"
            keys = await self.client.keys(pattern)

            stats = {
                "group_id": group_id,
                "total_requests": len(keys),
                "window_seconds": self.window,
                "limit_per_user": self.default_limit,
            }

            return stats

        except Exception as e:
            logger.error(f"Failed to get group stats: {e}")
            return {}


class SummaryJobQueue:
    """Manages summary job queue in Redis."""

    def __init__(self, redis_client: aioredis.Redis):
        """
        Initialize job queue.

        Args:
            redis_client: Redis async client
        """
        self.client = redis_client
        self.queue_key = "summary_jobs:queue"

    async def enqueue(
        self,
        group_id: int,
        user_id: int,
        requested_at: Optional[datetime] = None,
    ) -> str:
        """
        Enqueue a summary job.

        Args:
            group_id: Telegram group ID
            user_id: User who requested the summary
            requested_at: When the request was made

        Returns:
            Job ID
        """
        try:
            job_id = f"job:{group_id}:{user_id}:{datetime.now().timestamp()}"
            job_data = {
                "job_id": job_id,
                "group_id": group_id,
                "user_id": user_id,
                "requested_at": (requested_at or datetime.now()).isoformat(),
                "status": "queued",
            }

            # Push to queue
            await self.client.rpush(self.queue_key, json.dumps(job_data))

            logger.info(f"Summary job queued: {job_id}")
            return job_id

        except Exception as e:
            logger.error(f"Failed to enqueue summary job: {e}")
            raise

    async def get_queue_length(self) -> int:
        """
        Get number of jobs in queue.

        Returns:
            Number of queued jobs
        """
        try:
            length = await self.client.llen(self.queue_key)
            return length or 0
        except Exception as e:
            logger.error(f"Failed to get queue length: {e}")
            return 0

    async def dequeue(self):
        """
        Dequeue a job from the queue.

        Returns:
            Job data or None
        """
        try:
            job_data = await self.client.lpop(self.queue_key)
            if job_data:
                return json.loads(job_data)
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue job: {e}")
            return None

    async def mark_completed(self, job_id: str, result: Dict[str, Any]) -> bool:
        """
        Mark a job as completed.

        Args:
            job_id: Job ID
            result: Job result

        Returns:
            True if successful
        """
        try:
            result_key = f"job_result:{job_id}"
            await self.client.set(result_key, json.dumps(result), ex=86400)  # 24h expiry
            return True
        except Exception as e:
            logger.error(f"Failed to mark job completed: {e}")
            return False

    async def mark_failed(self, job_id: str, error_message: str) -> bool:
        """
        Mark a job as failed.

        Args:
            job_id: Job ID
            error_message: Error message

        Returns:
            True if successful
        """
        try:
            error_key = f"job_error:{job_id}"
            await self.client.set(error_key, json.dumps({"error": error_message}), ex=86400)
            return True
        except Exception as e:
            logger.error(f"Failed to mark job failed: {e}")
            return False


class CommandHandler:
    """Handles bot commands with authorization and rate limiting."""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        admin_user_ids: Optional[list[int]] = None,
        rate_limit_per_group: int = 10,
    ):
        """
        Initialize command handler.

        Args:
            redis_url: Redis connection URL (optional)
            admin_user_ids: List of admin user IDs
            rate_limit_per_group: Rate limit per group per hour
        """
        self.authorizer = CommandAuthorizer(admin_user_ids)
        self.redis = None  # Can be set for testing
        if redis_url:
            self.rate_limiter = RedisRateLimiter(
                redis_url=redis_url,
                default_limit_per_group=rate_limit_per_group,
                window_seconds=3600,  # 1 hour
            )
        else:
            self.rate_limiter = None
        self.job_queue: Optional[SummaryJobQueue] = None

    async def initialize(self) -> None:
        """Initialize command handler resources."""
        await self.rate_limiter.connect()
        self.job_queue = SummaryJobQueue(self.rate_limiter.client)
        logger.info("Command handler initialized")

    async def shutdown(self) -> None:
        """Cleanup command handler resources."""
        await self.rate_limiter.disconnect()
        logger.info("Command handler shut down")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /start command.

        Displays welcome message and bot capabilities.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        try:
            if not update.message or not update.effective_user:
                logger.warning("Start command: missing message or user")
                return

            user = update.effective_user
            if not self.authorizer.is_user_valid(user):
                logger.warning(f"Invalid user in start command: {user.id}")
                await update.message.reply_text(
                    "❌ Invalid user. Please try again."
                )
                return

            logger.info(f"User {user.id} ({user.full_name}) started bot")

            welcome_text = (
                "👋 <b>Welcome to GroupMind!</b>\n\n"
                "I'm your intelligent group chat assistant. Here's what I can do:\n\n"
                "📊 <b>Summarize Conversations</b>\n"
                "Get concise summaries of group discussions\n\n"
                "🧠 <b>Extract Insights</b>\n"
                "Identify key topics and discussion themes\n\n"
                "⚡ <b>Answer Questions</b>\n"
                "Respond to questions about recent chat topics\n\n"
                "🔒 <b>Privacy First</b>\n"
                "Your data is secure and never shared\n\n"
                "Use /help to learn more about available commands."
            )

            await update.message.reply_text(
                welcome_text,
                parse_mode="HTML",
            )

        except TelegramError as e:
            logger.error(f"Telegram error in start command: {e}")
            try:
                await update.message.reply_text(
                    "❌ Failed to send message. Please try again later."
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Unexpected error in start command: {e}")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /help command.

        Displays usage instructions and privacy notice.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        try:
            if not update.message or not update.effective_user:
                logger.warning("Help command: missing message or user")
                return

            user = update.effective_user
            if not self.authorizer.is_user_valid(user):
                logger.warning(f"Invalid user in help command: {user.id}")
                return

            logger.info(f"User {user.id} requested help")

            help_text = (
                "<b>📚 GroupMind Commands</b>\n\n"
                "<code>/start</code> - Welcome and bot overview\n"
                "<code>/help</code> - Show this help message\n"
                "<code>/summary</code> - Generate summary of recent group messages\n\n"
                "<b>💡 How to Use</b>\n"
                "1. Add me to your group\n"
                "2. I'll monitor conversations automatically\n"
                "3. Use <code>/summary</code> to get insights whenever you need\n\n"
                "<b>🔒 Privacy & Security</b>\n"
                "• All data is encrypted in transit\n"
                "• Messages are only stored for processing\n"
                "• You can remove me anytime\n"
                "• Admin data is never sold or shared\n\n"
                "<b>⚙️ Rate Limits</b>\n"
                "• 10 summary requests per group per hour\n"
                "• Helps prevent abuse and keep service fast\n\n"
                "Questions? Contact: @groupmind_support"
            )

            await update.message.reply_text(
                help_text,
                parse_mode="HTML",
            )

        except TelegramError as e:
            logger.error(f"Telegram error in help command: {e}")
            try:
                await update.message.reply_text(
                    "❌ Failed to send message. Please try again later."
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Unexpected error in help command: {e}")

    async def summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle /summary command.

        Queues a summary job and returns processing message with rate limiting.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        try:
            if not update.message or not update.effective_user or not update.effective_chat:
                logger.warning("Summary command: missing message, user, or chat")
                return

            user = update.effective_user
            chat = update.effective_chat

            # Validate user
            if not self.authorizer.is_user_valid(user):
                logger.warning(f"Invalid user in summary command: {user.id}")
                await update.message.reply_text(
                    "❌ Invalid user. Please try again."
                )
                return

            # Validate group
            if not self.authorizer.is_group_valid(chat):
                logger.warning(f"Invalid group in summary command: {chat.id}")
                await update.message.reply_text(
                    "❌ This command can only be used in groups."
                )
                return

            logger.info(f"Summary requested by {user.id} in group {chat.id}")

            # Check rate limit
            is_limited = await self.rate_limiter.is_rate_limited(
                group_id=chat.id,
                command="summary",
                user_id=user.id,
            )

            if is_limited:
                reset_time = await self.rate_limiter.get_reset_time(
                    group_id=chat.id,
                    command="summary",
                    user_id=user.id,
                )

                reset_str = ""
                if reset_time:
                    reset_str = f" (resets in ~{reset_time // 60} minutes)"

                error_text = (
                    f"⏱️ <b>Rate Limit Exceeded</b>\n\n"
                    f"You've reached the limit of 10 summaries per group per hour{reset_str}.\n"
                    f"Please try again later."
                )

                await update.message.reply_text(
                    error_text,
                    parse_mode="HTML",
                )
                return

            # Show typing indicator
            try:
                await update.effective_chat.send_action("typing")
            except Exception as e:
                logger.warning(f"Failed to send typing action: {e}")

            # Queue summary job
            try:
                if not self.job_queue:
                    raise RuntimeError("Job queue not initialized")

                job_id = await self.job_queue.enqueue(
                    group_id=chat.id,
                    user_id=user.id,
                    requested_at=datetime.now(),
                )

                queue_length = await self.job_queue.get_queue_length()

                processing_text = (
                    "⏳ <b>Processing Summary</b>\n\n"
                    "I'm analyzing recent messages in your group.\n"
                    f"Queue position: #{queue_length}\n\n"
                    "This usually takes 30-60 seconds.\n"
                    "I'll send you the summary when it's ready."
                )

                await update.message.reply_text(
                    processing_text,
                    parse_mode="HTML",
                )

                logger.info(f"Summary job {job_id} queued successfully")

            except Exception as e:
                logger.error(f"Failed to queue summary job: {e}")
                await update.message.reply_text(
                    "❌ Failed to queue summary. Please try again later."
                )

        except TelegramError as e:
            logger.error(f"Telegram error in summary command: {e}")
            try:
                await update.message.reply_text(
                    "❌ Failed to process summary. Please try again later."
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Unexpected error in summary command: {e}")

    async def handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle errors from invalid commands.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        try:
            if not update.message:
                logger.warning("Error handler: no message")
                return

            logger.warning(
                f"Unknown command or error from user {update.effective_user.id}: "
                f"{update.message.text}"
            )

            error_text = (
                "❓ <b>Unknown Command</b>\n\n"
                "I didn't recognize that command.\n\n"
                "Available commands:\n"
                "<code>/start</code> - Welcome message\n"
                "<code>/help</code> - Usage instructions\n"
                "<code>/summary</code> - Generate summary\n\n"
                "Use /help for more information."
            )

            await update.message.reply_text(
                error_text,
                parse_mode="HTML",
            )

        except TelegramError as e:
            logger.error(f"Telegram error in error handler: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in error handler: {e}")

    async def get_group_stats(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Get rate limit statistics for a group (admin only).

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        try:
            if not update.message or not update.effective_user or not update.effective_chat:
                return

            user = update.effective_user

            # Check admin permission
            if not self.authorizer.is_admin(user.id):
                logger.warning(f"Non-admin {user.id} tried to access stats")
                await update.message.reply_text(
                    "❌ You don't have permission to access this command."
                )
                return

            chat = update.effective_chat
            stats = await self.rate_limiter.get_group_stats(chat.id)

            stats_text = (
                f"<b>📊 Rate Limit Stats</b>\n\n"
                f"Group ID: <code>{stats.get('group_id')}</code>\n"
                f"Total Requests: {stats.get('total_requests', 0)}\n"
                f"Window: {stats.get('window_seconds', 0)} seconds\n"
                f"Limit per User: {stats.get('limit_per_user', 0)}\n"
            )

            await update.message.reply_text(
                stats_text,
                parse_mode="HTML",
            )

        except Exception as e:
            logger.error(f"Error in get_group_stats: {e}")
