"""
Redis queue management for GroupMind bot.

This module provides:
- Redis connection management
- Async job queuing for summary processing
- Job status tracking (pending, processing, completed, failed)
- Retry mechanism for failed jobs
- Queue statistics and monitoring
- Error handling for Redis connection issues
"""

import logging
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from enum import Enum

import redis.asyncio as aioredis
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"


class Job(BaseModel):
    """Job data model."""
    job_id: str
    status: JobStatus
    job_type: str  # e.g., "summary", "sentiment_analysis"
    group_id: int
    user_id: int
    data: Dict[str, Any]
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None

    class Config:
        """Pydantic config."""
        use_enum_values = True


class QueueStatistics(BaseModel):
    """Queue statistics."""
    total_jobs: int
    pending_jobs: int
    processing_jobs: int
    completed_jobs: int
    failed_jobs: int
    retry_jobs: int
    average_processing_time: float
    error_rate: float
    oldest_pending_job_age_seconds: Optional[int] = None


class RedisConnectionManager:
    """Manages Redis connections with error handling."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        """
        Initialize Redis connection manager.

        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        self.client: Optional[aioredis.Redis] = None
        self.is_connected = False

    async def connect(self) -> bool:
        """
        Establish connection to Redis.

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client = await aioredis.from_url(
                self.redis_url,
                encoding="utf8",
                decode_responses=True,
            )
            # Test connection
            await self.client.ping()
            self.is_connected = True
            logger.info("Connected to Redis successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.is_connected = False
            return False

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self.client:
            try:
                await self.client.close()
                self.is_connected = False
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")

    async def healthcheck(self) -> bool:
        """
        Check Redis connection health.

        Returns:
            True if connected and healthy, False otherwise
        """
        if not self.client:
            return False

        try:
            await self.client.ping()
            return True
        except Exception as e:
            logger.warning(f"Redis healthcheck failed: {e}")
            self.is_connected = False
            return False

    async def reconnect(self) -> bool:
        """
        Attempt to reconnect to Redis.

        Returns:
            True if successful, False otherwise
        """
        await self.disconnect()
        return await self.connect()


class JobQueue:
    """Async job queue using Redis."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        queue_prefix: str = "queue",
        job_prefix: str = "job",
    ):
        """
        Initialize job queue.

        Args:
            redis_client: Redis async client
            queue_prefix: Prefix for queue keys
            job_prefix: Prefix for job keys
        """
        self.redis = redis_client
        self.queue_prefix = queue_prefix
        self.job_prefix = job_prefix

    def _get_queue_key(self, job_type: str) -> str:
        """Get Redis key for job type queue."""
        return f"{self.queue_prefix}:{job_type}"

    def _get_job_key(self, job_id: str) -> str:
        """Get Redis key for job data."""
        return f"{self.job_prefix}:{job_id}"

    def _get_status_key(self, status: JobStatus) -> str:
        """Get Redis key for jobs by status."""
        return f"{self.queue_prefix}:status:{status.value}"

    def _get_stats_key(self) -> str:
        """Get Redis key for queue statistics."""
        return f"{self.queue_prefix}:stats"

    async def enqueue(
        self,
        job_type: str,
        group_id: int,
        user_id: int,
        data: Dict[str, Any],
        max_retries: int = 3,
    ) -> str:
        """
        Enqueue a new job.

        Args:
            job_type: Type of job (e.g., "summary")
            group_id: Group ID
            user_id: User ID
            data: Job-specific data
            max_retries: Maximum retry attempts

        Returns:
            Job ID
        """
        try:
            job_id = str(uuid.uuid4())

            job = Job(
                job_id=job_id,
                status=JobStatus.PENDING,
                job_type=job_type,
                group_id=group_id,
                user_id=user_id,
                data=data,
                created_at=datetime.utcnow(),
                max_retries=max_retries,
            )

            # Store job data
            job_key = self._get_job_key(job_id)
            await self.redis.set(
                job_key,
                job.json(),
                ex=24 * 3600,  # 24 hour expiration
            )

            # Add to queue
            queue_key = self._get_queue_key(job_type)
            await self.redis.rpush(queue_key, job_id)

            # Add to status index
            status_key = self._get_status_key(JobStatus.PENDING)
            await self.redis.sadd(status_key, job_id)

            # Update stats
            await self._update_stats("enqueued")

            logger.info(f"Job enqueued: {job_id} (type={job_type}, group={group_id})")
            return job_id

        except Exception as e:
            logger.error(f"Failed to enqueue job: {e}")
            raise

    async def dequeue(self, job_type: str, timeout: int = 0) -> Optional[Job]:
        """
        Dequeue a job from queue.

        Args:
            job_type: Type of job to dequeue
            timeout: Blocking timeout in seconds (0 = non-blocking)

        Returns:
            Job object or None if queue is empty
        """
        try:
            queue_key = self._get_queue_key(job_type)

            if timeout > 0:
                # Blocking pop with timeout
                result = await self.redis.blpop(queue_key, timeout)
                if not result:
                    return None
                job_id = result[1]
            else:
                # Non-blocking pop
                job_id = await self.redis.lpop(queue_key)
                if not job_id:
                    return None

            # Get job data
            job_key = self._get_job_key(job_id)
            job_data = await self.redis.get(job_key)

            if not job_data:
                logger.warning(f"Job data not found for ID: {job_id}")
                return None

            job = Job.parse_raw(job_data)

            # Update status
            old_status_key = self._get_status_key(job.status)
            await self.redis.srem(old_status_key, job_id)

            job.status = JobStatus.PROCESSING
            job.started_at = datetime.utcnow()

            # Save updated job
            await self.redis.set(job_key, job.json(), ex=24 * 3600)

            # Add to processing status
            new_status_key = self._get_status_key(JobStatus.PROCESSING)
            await self.redis.sadd(new_status_key, job_id)

            await self._update_stats("started")

            logger.debug(f"Job dequeued: {job_id}")
            return job

        except Exception as e:
            logger.error(f"Failed to dequeue job: {e}")
            return None

    async def mark_completed(
        self,
        job_id: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Mark job as completed.

        Args:
            job_id: Job ID
            result: Job result

        Returns:
            True if successful, False otherwise
        """
        try:
            job_key = self._get_job_key(job_id)
            job_data = await self.redis.get(job_key)

            if not job_data:
                logger.warning(f"Job not found: {job_id}")
                return False

            job = Job.parse_raw(job_data)

            # Update job
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.result = result

            # Save updated job
            await self.redis.set(job_key, job.json(), ex=24 * 3600)

            # Update status indices
            old_status_key = self._get_status_key(JobStatus.PROCESSING)
            await self.redis.srem(old_status_key, job_id)

            new_status_key = self._get_status_key(JobStatus.COMPLETED)
            await self.redis.sadd(new_status_key, job_id)

            await self._update_stats("completed")

            logger.info(f"Job completed: {job_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to mark job completed: {e}")
            return False

    async def mark_failed(
        self,
        job_id: str,
        error_message: str,
        should_retry: bool = True,
    ) -> bool:
        """
        Mark job as failed and optionally retry.

        Args:
            job_id: Job ID
            error_message: Error message
            should_retry: Whether to retry this job

        Returns:
            True if successful, False otherwise
        """
        try:
            job_key = self._get_job_key(job_id)
            job_data = await self.redis.get(job_key)

            if not job_data:
                logger.warning(f"Job not found: {job_id}")
                return False

            job = Job.parse_raw(job_data)
            job.error_message = error_message

            # Decide on retry
            if should_retry and job.retry_count < job.max_retries:
                job.status = JobStatus.RETRY
                job.retry_count += 1

                # Re-queue the job
                queue_key = self._get_queue_key(job.job_type)
                await self.redis.rpush(queue_key, job_id)

                # Update status
                status_key = self._get_status_key(JobStatus.RETRY)
                await self.redis.sadd(status_key, job_id)

                logger.warning(
                    f"Job will retry: {job_id} "
                    f"(attempt {job.retry_count}/{job.max_retries})"
                )
            else:
                job.status = JobStatus.FAILED
                job.completed_at = datetime.utcnow()

                # Update status
                status_key = self._get_status_key(JobStatus.FAILED)
                await self.redis.sadd(status_key, job_id)

                logger.error(f"Job failed permanently: {job_id} - {error_message}")

            # Save updated job
            await self.redis.set(job_key, job.json(), ex=24 * 3600)

            # Remove from processing
            processing_key = self._get_status_key(JobStatus.PROCESSING)
            await self.redis.srem(processing_key, job_id)

            await self._update_stats("failed")
            return True

        except Exception as e:
            logger.error(f"Failed to mark job failed: {e}")
            return False

    async def get_job(self, job_id: str) -> Optional[Job]:
        """
        Get job by ID.

        Args:
            job_id: Job ID

        Returns:
            Job object or None if not found
        """
        try:
            job_key = self._get_job_key(job_id)
            job_data = await self.redis.get(job_key)

            if not job_data:
                return None

            return Job.parse_raw(job_data)

        except Exception as e:
            logger.error(f"Failed to get job: {e}")
            return None

    async def get_queue_length(self, job_type: str) -> int:
        """
        Get number of pending jobs in queue.

        Args:
            job_type: Type of job

        Returns:
            Number of jobs
        """
        try:
            queue_key = self._get_queue_key(job_type)
            length = await self.redis.llen(queue_key)
            return length or 0
        except Exception as e:
            logger.error(f"Failed to get queue length: {e}")
            return 0

    async def get_jobs_by_status(
        self,
        status: JobStatus,
        limit: Optional[int] = None,
    ) -> List[Job]:
        """
        Get jobs by status.

        Args:
            status: Job status
            limit: Maximum jobs to return

        Returns:
            List of jobs
        """
        try:
            status_key = self._get_status_key(status)
            job_ids = await self.redis.smembers(status_key)

            if limit:
                job_ids = list(job_ids)[:limit]

            jobs = []
            for job_id in job_ids:
                job = await self.get_job(job_id)
                if job:
                    jobs.append(job)

            return jobs

        except Exception as e:
            logger.error(f"Failed to get jobs by status: {e}")
            return []

    async def get_statistics(self) -> QueueStatistics:
        """
        Get queue statistics.

        Returns:
            QueueStatistics object
        """
        try:
            # Count jobs by status
            pending = len(await self.redis.smembers(self._get_status_key(JobStatus.PENDING)))
            processing = len(await self.redis.smembers(self._get_status_key(JobStatus.PROCESSING)))
            completed = len(await self.redis.smembers(self._get_status_key(JobStatus.COMPLETED)))
            failed = len(await self.redis.smembers(self._get_status_key(JobStatus.FAILED)))
            retry = len(await self.redis.smembers(self._get_status_key(JobStatus.RETRY)))

            total = pending + processing + completed + failed + retry

            # Calculate error rate
            error_rate = 0.0
            if total > 0:
                error_rate = (failed + retry) / total

            # Get average processing time
            stats_data = await self.redis.hgetall(self._get_stats_key())
            avg_processing_time = 0.0
            if stats_data.get("completed_count", "0") and stats_data.get("total_processing_time", "0"):
                try:
                    completed_count = int(stats_data.get("completed_count", 0))
                    total_time = float(stats_data.get("total_processing_time", 0))
                    if completed_count > 0:
                        avg_processing_time = total_time / completed_count
                except (ValueError, ZeroDivisionError):
                    pass

            # Get oldest pending job
            oldest_pending_age = None
            pending_jobs = await self.redis.smembers(self._get_status_key(JobStatus.PENDING))
            if pending_jobs:
                oldest_job = None
                oldest_time = None
                for job_id in pending_jobs:
                    job = await self.get_job(job_id)
                    if job:
                        if oldest_time is None or job.created_at < oldest_time:
                            oldest_time = job.created_at
                            oldest_job = job

                if oldest_job:
                    age = datetime.utcnow() - oldest_job.created_at
                    oldest_pending_age = int(age.total_seconds())

            return QueueStatistics(
                total_jobs=total,
                pending_jobs=pending,
                processing_jobs=processing,
                completed_jobs=completed,
                failed_jobs=failed,
                retry_jobs=retry,
                average_processing_time=avg_processing_time,
                error_rate=error_rate,
                oldest_pending_job_age_seconds=oldest_pending_age,
            )

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return QueueStatistics(
                total_jobs=0,
                pending_jobs=0,
                processing_jobs=0,
                completed_jobs=0,
                failed_jobs=0,
                retry_jobs=0,
                average_processing_time=0.0,
                error_rate=0.0,
            )

    async def clear_queue(self, job_type: str) -> int:
        """
        Clear all jobs from a queue.

        Args:
            job_type: Type of job

        Returns:
            Number of jobs cleared
        """
        try:
            queue_key = self._get_queue_key(job_type)
            count = await self.redis.llen(queue_key)
            await self.redis.delete(queue_key)

            logger.info(f"Cleared {count} jobs from {job_type} queue")
            return count or 0

        except Exception as e:
            logger.error(f"Failed to clear queue: {e}")
            return 0

    async def cleanup_old_jobs(self, days_old: int = 7) -> int:
        """
        Clean up old completed/failed jobs.

        Args:
            days_old: Jobs older than this many days will be removed

        Returns:
            Number of jobs cleaned up
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            cleaned = 0

            # Clean completed jobs
            completed_jobs = await self.get_jobs_by_status(JobStatus.COMPLETED)
            for job in completed_jobs:
                if job.completed_at and job.completed_at < cutoff_date:
                    job_key = self._get_job_key(job.job_id)
                    await self.redis.delete(job_key)
                    cleaned += 1

            # Clean failed jobs
            failed_jobs = await self.get_jobs_by_status(JobStatus.FAILED)
            for job in failed_jobs:
                if job.completed_at and job.completed_at < cutoff_date:
                    job_key = self._get_job_key(job.job_id)
                    await self.redis.delete(job_key)
                    cleaned += 1

            logger.info(f"Cleaned up {cleaned} old jobs")
            return cleaned

        except Exception as e:
            logger.error(f"Failed to cleanup old jobs: {e}")
            return 0

    async def _update_stats(self, event: str) -> None:
        """
        Update queue statistics.

        Args:
            event: Type of event (enqueued, started, completed, failed)
        """
        try:
            stats_key = self._get_stats_key()

            if event == "enqueued":
                await self.redis.hincrby(stats_key, "total_enqueued", 1)
            elif event == "started":
                await self.redis.hincrby(stats_key, "total_started", 1)
            elif event == "completed":
                await self.redis.hincrby(stats_key, "completed_count", 1)
            elif event == "failed":
                await self.redis.hincrby(stats_key, "failed_count", 1)

            # Update timestamp
            await self.redis.hset(stats_key, "last_updated", datetime.utcnow().isoformat())

        except Exception as e:
            logger.warning(f"Failed to update stats: {e}")


# Export classes
__all__ = [
    "JobStatus",
    "Job",
    "QueueStatistics",
    "RedisConnectionManager",
    "JobQueue",
]
