"""
Message handlers for Telegram bot.

This module provides handlers for:
- Async message processing for group messages
- Filtering out bot commands and system messages
- Queuing messages to Redis with group_id and timestamp
- Message batching with max 1000 messages per group
- Privacy controls for opted-out users
- Performance optimization with async Redis operations
"""

import logging
import json
from datetime import datetime
from typing import Optional, Dict, List, Any

import redis.asyncio as aioredis
from telegram import Update, Message, Chat, User
from telegram.ext import ContextTypes
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


class PrivacyManager:
    """Manages user privacy preferences and opt-outs."""

    def __init__(self, redis_client: aioredis.Redis):
        """
        Initialize privacy manager.

        Args:
            redis_client: Redis async client
        """
        self.client = redis_client
        self.opted_out_key = "privacy:opted_out_users"
        self.group_opt_outs_key = "privacy:group_opt_outs"

    async def is_user_opted_out(self, user_id: int) -> bool:
        """
        Check if user has opted out of message recording.

        Args:
            user_id: Telegram user ID

        Returns:
            True if user opted out, False otherwise
        """
        try:
            is_member = await self.client.sismember(
                self.opted_out_key,
                str(user_id),
            )
            return bool(is_member)
        except Exception as e:
            logger.error(f"Failed to check user opt-out status: {e}")
            # Fail open - don't record if we can't verify
            return True

    async def opt_out_user(self, user_id: int) -> None:
        """
        Mark user as opted out.

        Args:
            user_id: Telegram user ID
        """
        try:
            await self.client.sadd(self.opted_out_key, str(user_id))
            logger.info(f"User {user_id} opted out")
        except Exception as e:
            logger.error(f"Failed to opt out user {user_id}: {e}")

    async def opt_in_user(self, user_id: int) -> None:
        """
        Mark user as opted in (remove from opt-out list).

        Args:
            user_id: Telegram user ID
        """
        try:
            await self.client.srem(self.opted_out_key, str(user_id))
            logger.info(f"User {user_id} opted in")
        except Exception as e:
            logger.error(f"Failed to opt in user {user_id}: {e}")

    async def is_group_opted_out(self, group_id: int) -> bool:
        """
        Check if a group has opted out completely.

        Args:
            group_id: Telegram group ID

        Returns:
            True if group opted out, False otherwise
        """
        try:
            is_member = await self.client.sismember(
                self.group_opt_outs_key,
                str(group_id),
            )
            return bool(is_member)
        except Exception as e:
            logger.error(f"Failed to check group opt-out status: {e}")
            return True

    async def opt_out_group(self, group_id: int) -> None:
        """
        Mark group as opted out.

        Args:
            group_id: Telegram group ID
        """
        try:
            await self.client.sadd(self.group_opt_outs_key, str(group_id))
            logger.info(f"Group {group_id} opted out")
        except Exception as e:
            logger.error(f"Failed to opt out group {group_id}: {e}")

    async def opt_in_group(self, group_id: int) -> None:
        """
        Mark group as opted in (remove from opt-out list).

        Args:
            group_id: Telegram group ID
        """
        try:
            await self.client.srem(self.group_opt_outs_key, str(group_id))
            logger.info(f"Group {group_id} opted in")
        except Exception as e:
            logger.error(f"Failed to opt in group {group_id}: {e}")


class MessageBatcher:
    """Manages message batching with size limits."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        max_messages_per_group: int = 1000,
    ):
        """
        Initialize message batcher.

        Args:
            redis_client: Redis async client
            max_messages_per_group: Maximum messages to store per group
        """
        self.client = redis_client
        self.max_messages = max_messages_per_group
        self.queue_prefix = "messages:queue"
        self.stats_prefix = "messages:stats"

    def _get_queue_key(self, group_id: int) -> str:
        """Get Redis key for group message queue."""
        return f"{self.queue_prefix}:group:{group_id}"

    def _get_stats_key(self, group_id: int) -> str:
        """Get Redis key for group message stats."""
        return f"{self.stats_prefix}:group:{group_id}"

    async def add_message(
        self,
        group_id: int,
        message_data: Dict[str, Any],
    ) -> bool:
        """
        Add message to batch queue.

        Args:
            group_id: Telegram group ID
            message_data: Message data dictionary

        Returns:
            True if added successfully, False otherwise
        """
        try:
            queue_key = self._get_queue_key(group_id)
            stats_key = self._get_stats_key(group_id)

            # Check current queue size
            current_size = await self.client.llen(queue_key)

            if current_size >= self.max_messages:
                # Remove oldest message (LPOP) to maintain max size
                await self.client.lpop(queue_key)
                logger.debug(
                    f"Removed oldest message from group {group_id} "
                    f"(queue at max {self.max_messages})"
                )

            # Add new message to the right (RPUSH)
            await self.client.rpush(queue_key, json.dumps(message_data))

            # Update stats
            await self.client.hincrbyfloat(stats_key, "total_messages", 1)
            await self.client.hset(
                stats_key,
                "last_updated",
                datetime.now().isoformat(),
            )

            logger.debug(
                f"Message added to group {group_id} queue "
                f"(size: {current_size + 1})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to add message to batch: {e}")
            return False

    async def get_messages(self, group_id: int, limit: Optional[int] = None) -> List[Dict]:
        """
        Get messages from queue.

        Args:
            group_id: Telegram group ID
            limit: Maximum number of messages to return

        Returns:
            List of message data dictionaries
        """
        try:
            queue_key = self._get_queue_key(group_id)
            limit = limit or self.max_messages

            # Get messages (LRANGE from 0 to -1 for all)
            messages_json = await self.client.lrange(queue_key, 0, limit - 1)

            messages = [
                json.loads(msg) for msg in messages_json
            ]

            return messages

        except Exception as e:
            logger.error(f"Failed to get messages from batch: {e}")
            return []

    async def clear_messages(self, group_id: int) -> int:
        """
        Clear all messages for a group.

        Args:
            group_id: Telegram group ID

        Returns:
            Number of messages cleared
        """
        try:
            queue_key = self._get_queue_key(group_id)
            stats_key = self._get_stats_key(group_id)

            # Get count before clearing
            count = await self.client.llen(queue_key)

            # Delete queue
            await self.client.delete(queue_key)

            # Reset stats
            await self.client.delete(stats_key)

            logger.info(f"Cleared {count} messages from group {group_id}")
            return count

        except Exception as e:
            logger.error(f"Failed to clear messages: {e}")
            return 0

    async def get_queue_size(self, group_id: int) -> int:
        """
        Get number of messages in queue.

        Args:
            group_id: Telegram group ID

        Returns:
            Number of messages
        """
        try:
            queue_key = self._get_queue_key(group_id)
            size = await self.client.llen(queue_key)
            return size or 0
        except Exception as e:
            logger.error(f"Failed to get queue size: {e}")
            return 0

    async def get_stats(self, group_id: int) -> Dict[str, Any]:
        """
        Get message statistics for a group.

        Args:
            group_id: Telegram group ID

        Returns:
            Statistics dictionary
        """
        try:
            queue_key = self._get_queue_key(group_id)
            stats_key = self._get_stats_key(group_id)

            queue_size = await self.client.llen(queue_key) or 0
            stats = await self.client.hgetall(stats_key)

            return {
                "group_id": group_id,
                "current_size": queue_size,
                "max_size": self.max_messages,
                "total_messages": stats.get("total_messages", "0"),
                "last_updated": stats.get("last_updated"),
            }

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}


class MessageFilter:
    """Filters messages for processing."""

    @staticmethod
    def should_skip_message(message: Message) -> bool:
        """
        Determine if message should be skipped.

        Args:
            message: Telegram message object

        Returns:
            True if message should be skipped, False to process
        """
        # Skip messages without text
        if not message.text:
            return True

        # Skip bot commands
        if message.text.startswith("/"):
            logger.debug("Skipping bot command message")
            return True

        # Skip system messages
        if message.new_chat_members:
            logger.debug("Skipping system message: new_chat_members")
            return True

        if message.left_chat_member:
            logger.debug("Skipping system message: left_chat_member")
            return True

        if message.new_chat_title:
            logger.debug("Skipping system message: new_chat_title")
            return True

        if message.new_chat_photo:
            logger.debug("Skipping system message: new_chat_photo")
            return True

        if message.delete_chat_photo:
            logger.debug("Skipping system message: delete_chat_photo")
            return True

        if message.group_chat_created:
            logger.debug("Skipping system message: group_chat_created")
            return True

        if message.supergroup_chat_created:
            logger.debug("Skipping system message: supergroup_chat_created")
            return True

        if message.channel_chat_created:
            logger.debug("Skipping system message: channel_chat_created")
            return True

        if message.message_auto_delete_timer_changed:
            logger.debug("Skipping system message: message_auto_delete_timer_changed")
            return True

        if message.pinned_message:
            logger.debug("Skipping system message: pinned_message")
            return True

        # Skip forwarded messages from external sources
        if message.forward_date and not message.forward_from_chat:
            logger.debug("Skipping forwarded message without source")
            return True

        return False

    @staticmethod
    def is_from_bot(user: User) -> bool:
        """
        Check if message is from a bot.

        Args:
            user: Telegram user object

        Returns:
            True if user is a bot, False otherwise
        """
        return user.is_bot if user else False


class MessageHandler:
    """Handles incoming group messages with filtering and queuing."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        max_messages_per_group: int = 1000,
    ):
        """
        Initialize message handler.

        Args:
            redis_client: Redis async client
            max_messages_per_group: Maximum messages to store per group
        """
        self.redis = redis_client
        self.batcher = MessageBatcher(redis_client, max_messages_per_group)
        self.privacy_manager = PrivacyManager(redis_client)
        self.filter = MessageFilter()

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handle incoming group message.

        Args:
            update: Telegram update object
            context: Telegram context object
        """
        try:
            # Validate message
            if not update.message or not update.effective_user or not update.effective_chat:
                logger.warning("Message handler: missing message, user, or chat")
                return

            message = update.message
            user = update.effective_user
            chat = update.effective_chat

            # Skip bot messages
            if self.filter.is_from_bot(user):
                logger.debug(f"Skipping message from bot {user.id}")
                return

            # Skip filtered messages
            if self.filter.should_skip_message(message):
                return

            # Skip if group opted out
            if await self.privacy_manager.is_group_opted_out(chat.id):
                logger.debug(f"Group {chat.id} has opted out")
                return

            # Skip if user opted out
            if await self.privacy_manager.is_user_opted_out(user.id):
                logger.debug(f"User {user.id} has opted out")
                return

            logger.info(
                f"Processing message from {user.id} ({user.first_name}) "
                f"in group {chat.id}: {message.text[:50]}..."
            )

            # Prepare message data
            message_data = await self._prepare_message_data(message, user, chat)

            # Add to queue
            success = await self.batcher.add_message(chat.id, message_data)

            if success:
                logger.debug(f"Message queued successfully from user {user.id}")
            else:
                logger.warning(f"Failed to queue message from user {user.id}")

        except TelegramError as e:
            logger.error(f"Telegram error in message handler: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in message handler: {e}")

    async def _prepare_message_data(
        self,
        message: Message,
        user: User,
        chat: Chat,
    ) -> Dict[str, Any]:
        """
        Prepare message data for storage.

        Args:
            message: Telegram message object
            user: Telegram user object
            chat: Telegram chat object

        Returns:
            Dictionary with message data
        """
        return {
            "message_id": message.message_id,
            "group_id": chat.id,
            "user_id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "text": message.text,
            "timestamp": message.date.isoformat() if message.date else datetime.now().isoformat(),
            "reply_to_message_id": message.reply_to_message.message_id
            if message.reply_to_message
            else None,
            "has_entities": bool(message.entities),
            "entity_types": [
                entity.type for entity in message.entities
            ] if message.entities else [],
        }

    async def get_group_messages(
        self, group_id: int, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get stored messages for a group.

        Args:
            group_id: Telegram group ID
            limit: Maximum number of messages to retrieve

        Returns:
            List of message dictionaries
        """
        try:
            messages = await self.batcher.get_messages(group_id, limit)
            logger.info(f"Retrieved {len(messages)} messages for group {group_id}")
            return messages
        except Exception as e:
            logger.error(f"Failed to get group messages: {e}")
            return []

    async def get_handler_stats(self, group_id: int) -> Dict[str, Any]:
        """
        Get message handler statistics.

        Args:
            group_id: Telegram group ID

        Returns:
            Statistics dictionary
        """
        try:
            stats = await self.batcher.get_stats(group_id)
            return stats
        except Exception as e:
            logger.error(f"Failed to get handler stats: {e}")
            return {}

    async def clear_group_messages(self, group_id: int) -> int:
        """
        Clear all stored messages for a group.

        Args:
            group_id: Telegram group ID

        Returns:
            Number of messages cleared
        """
        try:
            count = await self.batcher.clear_messages(group_id)
            logger.info(f"Cleared {count} messages from group {group_id}")
            return count
        except Exception as e:
            logger.error(f"Failed to clear group messages: {e}")
            return 0
