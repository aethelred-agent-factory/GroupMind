"""
Rate limiting service for GroupMind bot.

This module provides:
- Token bucket algorithm implementation
- Rate limits per group and per user
- Redis-backed rate limiting for scalability
- Different limits for free vs paid tiers
- Proper headers and response when rate limited
- Async/await compatible
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from enum import Enum

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class UserTier(str, Enum):
    """User subscription tier."""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class RateLimitConfig:
    """Rate limit configuration by tier."""

    CONFIGS = {
        UserTier.FREE: {
            # Summaries per group per day
            "summaries_per_group_per_day": 1,
            # Total summaries per user per day
            "summaries_per_user_per_day": 5,
            # Messages that trigger processing per group per hour
            "messages_per_group_per_hour": 1000,
            # Concurrent jobs per user
            "concurrent_jobs": 1,
            # Burst allowance (extra requests in short time)
            "burst_multiplier": 1.0,
        },
        UserTier.PRO: {
            "summaries_per_group_per_day": 10,
            "summaries_per_user_per_day": 50,
            "messages_per_group_per_hour": 5000,
            "concurrent_jobs": 5,
            "burst_multiplier": 1.5,
        },
        UserTier.ENTERPRISE: {
            "summaries_per_group_per_day": 100,
            "summaries_per_user_per_day": 500,
            "messages_per_group_per_hour": 50000,
            "concurrent_jobs": 50,
            "burst_multiplier": 2.0,
        },
    }

    @classmethod
    def get(cls, tier: UserTier) -> Dict:
        """Get config for tier."""
        return cls.CONFIGS.get(tier, cls.CONFIGS[UserTier.FREE])


class RateLimitHeaders:
    """Rate limit response headers."""

    def __init__(
        self,
        limit: int,
        remaining: int,
        reset_at: datetime,
        retry_after_seconds: Optional[int] = None,
    ):
        """
        Initialize headers.

        Args:
            limit: Total requests allowed
            remaining: Remaining requests
            reset_at: When limit resets
            retry_after_seconds: Seconds to wait before retry
        """
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at
        self.retry_after_seconds = retry_after_seconds

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(self.reset_at.timestamp())),
        }

        if self.retry_after_seconds:
            headers["Retry-After"] = str(self.retry_after_seconds)

        return headers


class TokenBucket:
    """Token bucket rate limiter."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        bucket_key: str,
        capacity: int,
        refill_rate: float,  # Tokens per second
        burst_multiplier: float = 1.0,
    ):
        """
        Initialize token bucket.

        Args:
            redis_client: Redis async client
            bucket_key: Unique key for this bucket
            capacity: Maximum tokens in bucket
            refill_rate: Tokens added per second
            burst_multiplier: Multiplier for burst capacity
        """
        self.redis = redis_client
        self.bucket_key = bucket_key
        self.capacity = capacity
        self.burst_capacity = int(capacity * burst_multiplier)
        self.refill_rate = refill_rate
        self.last_refill_key = f"{bucket_key}:last_refill"
        self.ttl = int((capacity / refill_rate) * 2) + 3600  # Long enough to cover refill period

    async def _initialize_bucket(self) -> None:
        """Initialize bucket if it doesn't exist."""
        exists = await self.redis.exists(self.bucket_key)
        if not exists:
            await self.redis.set(
                self.bucket_key,
                self.burst_capacity,
                ex=self.ttl,
            )
            await self.redis.set(
                self.last_refill_key,
                datetime.utcnow().timestamp(),
                ex=self.ttl,
            )

    async def _refill(self) -> Tuple[float, float]:
        """
        Refill tokens based on time elapsed.

        Returns:
            Tuple of (current_tokens, tokens_added)
        """
        await self._initialize_bucket()

        # Get current state
        tokens_str = await self.redis.get(self.bucket_key)
        last_refill_str = await self.redis.get(self.last_refill_key)

        current_tokens = float(tokens_str or self.burst_capacity)
        last_refill = float(last_refill_str or datetime.utcnow().timestamp())

        # Calculate time elapsed
        now = datetime.utcnow().timestamp()
        time_elapsed = now - last_refill

        # Add tokens
        tokens_to_add = time_elapsed * self.refill_rate
        new_tokens = min(current_tokens + tokens_to_add, self.burst_capacity)

        # Update Redis
        await self.redis.set(self.bucket_key, new_tokens, ex=self.ttl)
        await self.redis.set(self.last_refill_key, now, ex=self.ttl)

        return new_tokens, tokens_to_add

    async def try_consume(self, tokens: float = 1.0) -> Tuple[bool, float]:
        """
        Try to consume tokens.

        Args:
            tokens: Number of tokens to consume

        Returns:
            Tuple of (success, tokens_available_after_request)
        """
        try:
            # Refill if needed
            current_tokens, _ = await self._refill()

            if current_tokens >= tokens:
                # Consume tokens
                new_tokens = current_tokens - tokens
                await self.redis.set(self.bucket_key, new_tokens, ex=self.ttl)
                return True, new_tokens
            else:
                return False, current_tokens

        except Exception as e:
            logger.error(f"Error in token bucket: {e}")
            # Fail open - allow request on error
            return True, self.capacity

    async def get_state(self) -> Dict:
        """Get current bucket state."""
        try:
            current_tokens, _ = await self._refill()
            reset_at = datetime.utcnow() + timedelta(seconds=(self.capacity - current_tokens) / self.refill_rate)

            return {
                "current_tokens": current_tokens,
                "capacity": self.capacity,
                "burst_capacity": self.burst_capacity,
                "refill_rate": self.refill_rate,
                "reset_at": reset_at,
            }
        except Exception as e:
            logger.error(f"Error getting bucket state: {e}")
            return {}


class UserRateLimiter:
    """Rate limiter for per-user limits."""

    def __init__(self, redis_client: aioredis.Redis):
        """
        Initialize user rate limiter.

        Args:
            redis_client: Redis async client
        """
        self.redis = redis_client
        self.prefix = "rate_limit:user"

    def _get_bucket_key(self, user_id: int, limit_type: str) -> str:
        """Get Redis key for user bucket."""
        return f"{self.prefix}:{user_id}:{limit_type}"

    async def check_summaries_per_day(
        self,
        user_id: int,
        tier: UserTier = UserTier.FREE,
    ) -> Tuple[bool, RateLimitHeaders]:
        """
        Check if user can create a summary today.

        Args:
            user_id: Telegram user ID
            tier: User subscription tier

        Returns:
            Tuple of (allowed, headers)
        """
        config = RateLimitConfig.get(tier)
        limit = config["summaries_per_user_per_day"]

        # Calculate refill rate (once per day)
        refill_rate = limit / 86400  # Tokens per second

        bucket_key = self._get_bucket_key(user_id, "summaries_per_day")
        bucket = TokenBucket(
            self.redis,
            bucket_key,
            capacity=limit,
            refill_rate=refill_rate,
            burst_multiplier=config["burst_multiplier"],
        )

        allowed, remaining = await bucket.try_consume(1.0)

        # Calculate reset time
        state = await bucket.get_state()
        reset_at = state.get("reset_at", datetime.utcnow() + timedelta(hours=24))

        headers = RateLimitHeaders(
            limit=limit,
            remaining=int(remaining),
            reset_at=reset_at,
            retry_after_seconds=None if allowed else int((1.0 / refill_rate) + 1),
        )

        return allowed, headers

    async def check_concurrent_jobs(
        self,
        user_id: int,
        tier: UserTier = UserTier.FREE,
    ) -> Tuple[bool, RateLimitHeaders]:
        """
        Check if user can have more concurrent jobs.

        Args:
            user_id: Telegram user ID
            tier: User subscription tier

        Returns:
            Tuple of (allowed, headers)
        """
        config = RateLimitConfig.get(tier)
        limit = config["concurrent_jobs"]

        bucket_key = self._get_bucket_key(user_id, "concurrent_jobs")

        # For concurrent jobs, use a simple counter
        try:
            current = await self.redis.incr(bucket_key)
            
            if current == 1:
                # Set expiration on first increment
                await self.redis.expire(bucket_key, 3600)  # 1 hour

            allowed = current <= limit
            remaining = max(0, limit - current)

            reset_at = datetime.utcnow() + timedelta(hours=1)

            headers = RateLimitHeaders(
                limit=limit,
                remaining=remaining,
                reset_at=reset_at,
                retry_after_seconds=None if allowed else 60,
            )

            return allowed, headers

        except Exception as e:
            logger.error(f"Error checking concurrent jobs: {e}")
            # Fail open
            return True, RateLimitHeaders(limit, limit, datetime.utcnow())

    async def release_concurrent_job(self, user_id: int) -> None:
        """Release a concurrent job slot."""
        bucket_key = self._get_bucket_key(user_id, "concurrent_jobs")
        await self.redis.decr(bucket_key)


class GroupRateLimiter:
    """Rate limiter for per-group limits."""

    def __init__(self, redis_client: aioredis.Redis):
        """
        Initialize group rate limiter.

        Args:
            redis_client: Redis async client
        """
        self.redis = redis_client
        self.prefix = "rate_limit:group"

    def _get_bucket_key(self, group_id: int, limit_type: str) -> str:
        """Get Redis key for group bucket."""
        return f"{self.prefix}:{group_id}:{limit_type}"

    async def check_summaries_per_day(
        self,
        group_id: int,
        tier: UserTier = UserTier.FREE,
    ) -> Tuple[bool, RateLimitHeaders]:
        """
        Check if group can create a summary today.

        Args:
            group_id: Telegram group ID
            tier: User subscription tier

        Returns:
            Tuple of (allowed, headers)
        """
        config = RateLimitConfig.get(tier)
        limit = config["summaries_per_group_per_day"]

        # Calculate refill rate (once per day)
        refill_rate = limit / 86400  # Tokens per second

        bucket_key = self._get_bucket_key(group_id, "summaries_per_day")
        bucket = TokenBucket(
            self.redis,
            bucket_key,
            capacity=limit,
            refill_rate=refill_rate,
            burst_multiplier=config["burst_multiplier"],
        )

        allowed, remaining = await bucket.try_consume(1.0)

        # Calculate reset time
        state = await bucket.get_state()
        reset_at = state.get("reset_at", datetime.utcnow() + timedelta(hours=24))

        headers = RateLimitHeaders(
            limit=limit,
            remaining=int(remaining),
            reset_at=reset_at,
            retry_after_seconds=None if allowed else int((1.0 / refill_rate) + 1),
        )

        return allowed, headers

    async def check_messages_per_hour(
        self,
        group_id: int,
        tier: UserTier = UserTier.FREE,
    ) -> Tuple[bool, RateLimitHeaders]:
        """
        Check message processing limit per hour.

        Args:
            group_id: Telegram group ID
            tier: User subscription tier

        Returns:
            Tuple of (allowed, headers)
        """
        config = RateLimitConfig.get(tier)
        limit = config["messages_per_group_per_hour"]

        # Calculate refill rate (per hour)
        refill_rate = limit / 3600  # Tokens per second

        bucket_key = self._get_bucket_key(group_id, "messages_per_hour")
        bucket = TokenBucket(
            self.redis,
            bucket_key,
            capacity=limit,
            refill_rate=refill_rate,
            burst_multiplier=config["burst_multiplier"],
        )

        allowed, remaining = await bucket.try_consume(1.0)

        # Calculate reset time
        state = await bucket.get_state()
        reset_at = state.get("reset_at", datetime.utcnow() + timedelta(hours=1))

        headers = RateLimitHeaders(
            limit=limit,
            remaining=int(remaining),
            reset_at=reset_at,
            retry_after_seconds=None if allowed else int((1.0 / refill_rate) + 1),
        )

        return allowed, headers


class CombinedRateLimiter:
    """Combined rate limiter for both user and group limits."""

    def __init__(self, redis_client: aioredis.Redis):
        """
        Initialize combined rate limiter.

        Args:
            redis_client: Redis async client
        """
        self.redis = redis_client
        self.user_limiter = UserRateLimiter(redis_client)
        self.group_limiter = GroupRateLimiter(redis_client)

    async def check_summary_request(
        self,
        user_id: int,
        group_id: int,
        tier: UserTier = UserTier.FREE,
    ) -> Tuple[bool, Dict[str, RateLimitHeaders], Optional[str]]:
        """
        Check if summary request is allowed.

        Checks both user and group limits.

        Args:
            user_id: Telegram user ID
            group_id: Telegram group ID
            tier: User subscription tier

        Returns:
            Tuple of (allowed, headers_dict, error_message)
        """
        try:
            headers_dict = {}

            # Check user limit
            user_allowed, user_headers = await self.user_limiter.check_summaries_per_day(
                user_id,
                tier,
            )
            headers_dict["user"] = user_headers

            if not user_allowed:
                return False, headers_dict, (
                    "You've reached your daily summary limit. "
                    "Try again tomorrow or upgrade your account."
                )

            # Check group limit
            group_allowed, group_headers = await self.group_limiter.check_summaries_per_day(
                group_id,
                tier,
            )
            headers_dict["group"] = group_headers

            if not group_allowed:
                return False, headers_dict, (
                    "This group has reached its daily summary limit. "
                    "Try again tomorrow."
                )

            # Check concurrent jobs
            concurrent_allowed, concurrent_headers = await self.user_limiter.check_concurrent_jobs(
                user_id,
                tier,
            )
            headers_dict["concurrent"] = concurrent_headers

            if not concurrent_allowed:
                return False, headers_dict, (
                    "You have too many processing jobs running. "
                    "Wait for some to complete."
                )

            return True, headers_dict, None

        except Exception as e:
            logger.error(f"Error checking rate limits: {e}")
            # Fail open
            return True, {}, None

    async def get_user_limits(
        self,
        user_id: int,
        tier: UserTier = UserTier.FREE,
    ) -> Dict[str, any]:
        """
        Get current user rate limit status.

        Args:
            user_id: Telegram user ID
            tier: User subscription tier

        Returns:
            Dictionary with limit statuses
        """
        try:
            summaries_allowed, summaries_headers = await self.user_limiter.check_summaries_per_day(
                user_id,
                tier,
            )
            concurrent_allowed, concurrent_headers = await self.user_limiter.check_concurrent_jobs(
                user_id,
                tier,
            )

            return {
                "summaries_per_day": {
                    "limit": summaries_headers.limit,
                    "remaining": summaries_headers.remaining,
                    "reset_at": summaries_headers.reset_at.isoformat(),
                },
                "concurrent_jobs": {
                    "limit": concurrent_headers.limit,
                    "remaining": concurrent_headers.remaining,
                    "reset_at": concurrent_headers.reset_at.isoformat(),
                },
            }

        except Exception as e:
            logger.error(f"Error getting user limits: {e}")
            return {}

    async def get_group_limits(
        self,
        group_id: int,
        tier: UserTier = UserTier.FREE,
    ) -> Dict[str, any]:
        """
        Get current group rate limit status.

        Args:
            group_id: Telegram group ID
            tier: User subscription tier

        Returns:
            Dictionary with limit statuses
        """
        try:
            summaries_allowed, summaries_headers = await self.group_limiter.check_summaries_per_day(
                group_id,
                tier,
            )
            messages_allowed, messages_headers = await self.group_limiter.check_messages_per_hour(
                group_id,
                tier,
            )

            return {
                "summaries_per_day": {
                    "limit": summaries_headers.limit,
                    "remaining": summaries_headers.remaining,
                    "reset_at": summaries_headers.reset_at.isoformat(),
                },
                "messages_per_hour": {
                    "limit": messages_headers.limit,
                    "remaining": messages_headers.remaining,
                    "reset_at": messages_headers.reset_at.isoformat(),
                },
            }

        except Exception as e:
            logger.error(f"Error getting group limits: {e}")
            return {}


# Export classes
__all__ = [
    "UserTier",
    "RateLimitConfig",
    "RateLimitHeaders",
    "TokenBucket",
    "UserRateLimiter",
    "GroupRateLimiter",
    "CombinedRateLimiter",
]
