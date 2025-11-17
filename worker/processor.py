"""
Summary job processor worker for GroupMind.

This module provides:
- Redis worker that processes summary jobs
- Batch processing during off-peak hours (configurable)
- DeepSeek API integration for summarization
- Database storage of generated summaries
- Notification to Telegram groups when summary is ready
- Error handling and job retry logic
- Resource management and graceful shutdown
"""

import logging
import asyncio
import signal
import os
from datetime import datetime, time
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from telegram import Bot
from telegram.error import TelegramError

# Import services and utilities
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bot.models.database import Base, Group, Message, Summary, User, AuditLog
from bot.models.schemas import SummaryCreate
from bot.services.deepseek import DeepSeekClient, SimpleSummaryGenerator, Message as DeepSeekMessage
from bot.services.summarizer import Summarizer, Language
from bot.services.sentiment import SentimentAnalyzer
from bot.utils.queue import RedisConnectionManager, JobQueue, JobStatus

logger = logging.getLogger(__name__)


class WorkerConfig:
    """Worker configuration."""

    def __init__(self):
        """Initialize configuration from environment."""
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.database_url = os.getenv("DATABASE_URL", "postgresql://localhost/groupmind")
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        self.batch_processing_hour = int(os.getenv("BATCH_PROCESSING_HOUR", "2"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.max_workers = int(os.getenv("MAX_WORKERS", "4"))
        self.job_timeout = int(os.getenv("JOB_TIMEOUT", "300"))  # 5 minutes

    def validate(self) -> bool:
        """Validate required configuration."""
        required = ["telegram_token", "deepseek_api_key"]
        missing = [field for field in required if not getattr(self, field)]
        if missing:
            logger.error(f"Missing required config: {', '.join(missing)}")
            return False
        return True


class SummaryProcessor:
    """Processes summary generation jobs."""

    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        telegram_bot: Bot,
        db_session_maker: sessionmaker,
        sentiment_analyzer: SentimentAnalyzer,
    ):
        """
        Initialize processor.

        Args:
            deepseek_client: DeepSeek API client
            telegram_bot: Telegram bot instance
            db_session_maker: Database session factory
            sentiment_analyzer: Sentiment analyzer instance
        """
        self.deepseek = deepseek_client
        self.bot = telegram_bot
        self.db_session_maker = db_session_maker
        self.sentiment_analyzer = sentiment_analyzer
        self.summarizer = Summarizer()
        self.simple_summarizer = SimpleSummaryGenerator()

    async def process_summary_job(
        self,
        group_id: int,
        user_id: int,
        job_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Process a summary generation job.

        Args:
            group_id: Telegram group ID
            user_id: User who requested summary
            job_data: Job-specific data

        Returns:
            Summary result dictionary
        """
        try:
            logger.info(f"Processing summary job for group {group_id}")

            async with self.db_session_maker() as session:
                # Fetch group
                group = await self._get_group(session, group_id)
                if not group:
                    raise ValueError(f"Group not found: {group_id}")

                # Fetch messages
                messages = await self._get_group_messages(
                    session,
                    group_id,
                    limit=job_data.get("limit", 1000),
                )

                if not messages:
                    logger.warning(f"No messages found for group {group_id}")
                    return {
                        "error": "No messages to summarize",
                        "group_id": group_id,
                    }

                # Convert to summary format
                summary_messages = [
                    DeepSeekMessage(
                        user=msg.get("username", f"User{msg['user_id']}"),
                        text=msg["text"],
                        timestamp=msg["timestamp"].isoformat() if msg["timestamp"] else None,
                    )
                    for msg in messages
                ]

                # Analyze conversation
                stats, formatted_context, was_truncated = self.summarizer.analyze_conversation(
                    messages
                )

                # Build prompt
                prompt, detected_language = self.summarizer.build_prompt(
                    stats,
                    formatted_context,
                )

                logger.info(
                    f"Generated prompt ({len(prompt)} chars) for group {group_id}, "
                    f"language={detected_language}"
                )

                # Generate summary using DeepSeek
                summary_response = await self.deepseek.summarize_messages(
                    summary_messages,
                )

                # Fallback to simple summary if AI fails
                if not summary_response:
                    logger.warning(f"DeepSeek failed, using fallback summary for group {group_id}")
                    fallback = self.simple_summarizer.generate_summary(summary_messages)
                    summary_text = fallback.summary
                    is_ai_generated = False
                    confidence_score = 0.5
                    model_used = "fallback"
                    key_topics = fallback.key_topics
                    action_items = fallback.action_items
                else:
                    summary_text = summary_response.summary
                    is_ai_generated = True
                    confidence_score = 0.9
                    model_used = "deepseek-chat"
                    key_topics = summary_response.key_topics or []
                    action_items = summary_response.action_items or []

                # Analyze sentiment
                sentiment_analysis = self.sentiment_analyzer.analyze_batch(
                    [msg["text"] for msg in messages]
                )

                # Create summary record
                summary = Summary(
                    summary_id=f"summary_{group_id}_{datetime.utcnow().timestamp()}",
                    group_id=group_id,
                    period_start=stats.start_time or datetime.utcnow(),
                    period_end=stats.end_time or datetime.utcnow(),
                    summary_text=summary_text,
                    message_count=stats.message_count,
                    participant_count=stats.participant_count,
                    sentiment_score=sentiment_analysis.get("average_score", 0.0),
                    dominant_sentiment=sentiment_analysis.get("overall_sentiment"),
                    key_topics=str(key_topics),
                    action_items=str(action_items),
                    language=detected_language.value,
                    model_used=model_used,
                    confidence_score=confidence_score,
                    is_ai_generated=is_ai_generated,
                    processed_at=datetime.utcnow(),
                )

                # Save to database
                session.add(summary)
                await session.flush()

                # Log audit event
                audit_log = AuditLog(
                    action="summary_generated",
                    entity_type="summary",
                    entity_id=summary.summary_id,
                    user_id=user_id,
                    details=f"Messages: {stats.message_count}, Participants: {stats.participant_count}",
                )
                session.add(audit_log)

                await session.commit()

                logger.info(f"Summary saved: {summary.summary_id}")

                # Notify group
                await self._notify_group(
                    group_id,
                    summary_text,
                    user_id,
                )

                return {
                    "summary_id": summary.summary_id,
                    "group_id": group_id,
                    "message_count": stats.message_count,
                    "participant_count": stats.participant_count,
                    "model_used": model_used,
                    "is_ai_generated": is_ai_generated,
                }

        except Exception as e:
            logger.error(f"Error processing summary job: {e}", exc_info=True)
            raise

    async def _get_group(self, session: AsyncSession, group_id: int) -> Optional[Group]:
        """Get group from database."""
        from sqlalchemy import select
        result = await session.execute(
            select(Group).where(Group.group_id == group_id)
        )
        return result.scalars().first()

    async def _get_group_messages(
        self,
        session: AsyncSession,
        group_id: int,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Get recent messages for group."""
        from sqlalchemy import select, desc
        result = await session.execute(
            select(Message)
            .where(Message.group_id == group_id)
            .where(Message.deleted_at.is_(None))
            .order_by(desc(Message.timestamp))
            .limit(limit)
        )

        messages = result.scalars().all()

        # Convert to dictionaries
        message_dicts = []
        for msg in messages:
            message_dicts.append({
                "message_id": msg.message_id,
                "user_id": msg.user_id,
                "username": msg.user.username if msg.user else f"User{msg.user_id}",
                "text": msg.text,
                "timestamp": msg.timestamp,
                "sentiment": msg.sentiment,
            })

        # Return in chronological order
        return list(reversed(message_dicts))

    async def _notify_group(
        self,
        group_id: int,
        summary_text: str,
        user_id: int,
    ) -> bool:
        """
        Send summary notification to group.

        Args:
            group_id: Telegram group ID
            summary_text: Summary content
            user_id: User who requested

        Returns:
            True if successful, False otherwise
        """
        try:
            notification = (
                "📊 <b>Group Summary Ready</b>\n\n"
                f"{summary_text}\n\n"
                "Requested by: <code>user</code>"
            )

            await self.bot.send_message(
                chat_id=group_id,
                text=notification,
                parse_mode="HTML",
            )

            logger.info(f"Summary notification sent to group {group_id}")
            return True

        except TelegramError as e:
            logger.error(f"Failed to notify group {group_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error notifying group: {e}")
            return False


class SummaryWorker:
    """Main worker process for processing summary jobs."""

    def __init__(self, config: WorkerConfig):
        """
        Initialize worker.

        Args:
            config: Worker configuration
        """
        self.config = config
        self.running = False
        self.redis_manager: Optional[RedisConnectionManager] = None
        self.job_queue: Optional[JobQueue] = None
        self.db_engine = None
        self.db_session_maker = None
        self.bot: Optional[Bot] = None
        self.processor: Optional[SummaryProcessor] = None
        self.sentiment_analyzer: Optional[SentimentAnalyzer] = None

        # Setup logging
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('worker.log'),
                logging.StreamHandler(),
            ]
        )

    async def initialize(self) -> bool:
        """
        Initialize worker resources.

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Initializing worker...")

            # Validate config
            if not self.config.validate():
                return False

            # Initialize Redis
            self.redis_manager = RedisConnectionManager(self.config.redis_url)
            if not await self.redis_manager.connect():
                logger.error("Failed to connect to Redis")
                return False

            self.job_queue = JobQueue(self.redis_manager.client)

            # Initialize database
            self.db_engine = create_async_engine(
                self.config.database_url,
                echo=False,
                pool_pre_ping=True,
                pool_size=20,
                max_overflow=10,
            )

            # Create tables
            async with self.db_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            self.db_session_maker = sessionmaker(
                self.db_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            # Initialize Telegram bot
            self.bot = Bot(token=self.config.telegram_token)

            # Initialize services
            deepseek_client = DeepSeekClient(
                api_key=self.config.deepseek_api_key,
            )
            await deepseek_client.initialize()

            self.sentiment_analyzer = SentimentAnalyzer()

            # Initialize processor
            self.processor = SummaryProcessor(
                deepseek_client=deepseek_client,
                telegram_bot=self.bot,
                db_session_maker=self.db_session_maker,
                sentiment_analyzer=self.sentiment_analyzer,
            )

            logger.info("Worker initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize worker: {e}", exc_info=True)
            return False

    async def run(self) -> None:
        """Run the worker."""
        try:
            self.running = True
            logger.info("Starting worker...")

            # Setup signal handlers
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

            # Start processing
            await self._process_jobs()

        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
        finally:
            await self.shutdown()

    async def _process_jobs(self) -> None:
        """Process jobs from queue."""
        logger.info("Starting job processing loop...")

        while self.running:
            try:
                # Check if in batch processing window
                if self._is_batch_processing_time():
                    await self._process_batch_jobs()
                else:
                    # Process jobs normally
                    job = await self.job_queue.dequeue("summary", timeout=5)

                    if job:
                        await self._handle_job(job)
                    else:
                        # No jobs, wait a bit
                        await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error in job processing loop: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _process_batch_jobs(self) -> None:
        """Process batch jobs during off-peak hours."""
        logger.info("Entering batch processing mode")

        # Get all pending jobs
        pending_jobs = await self.job_queue.get_jobs_by_status(JobStatus.PENDING)
        logger.info(f"Processing {len(pending_jobs)} batched jobs")

        for job in pending_jobs:
            if not self.running:
                break

            await self._handle_job(job)

        logger.info("Batch processing complete")

    async def _handle_job(self, job) -> None:
        """
        Handle a job.

        Args:
            job: Job to process
        """
        try:
            logger.info(f"Processing job {job.job_id}...")

            # Execute job with timeout
            try:
                result = await asyncio.wait_for(
                    self.processor.process_summary_job(
                        group_id=job.group_id,
                        user_id=job.user_id,
                        job_data=job.data,
                    ),
                    timeout=self.config.job_timeout,
                )

                # Mark job as completed
                await self.job_queue.mark_completed(job.job_id, result)

            except asyncio.TimeoutError:
                logger.error(f"Job {job.job_id} timed out")
                await self.job_queue.mark_failed(
                    job.job_id,
                    "Job execution timed out",
                    should_retry=True,
                )

        except Exception as e:
            logger.error(f"Error handling job {job.job_id}: {e}", exc_info=True)
            await self.job_queue.mark_failed(
                job.job_id,
                str(e),
                should_retry=True,
            )

    def _is_batch_processing_time(self) -> bool:
        """
        Check if current time is in batch processing window.

        Returns:
            True if in batch processing time, False otherwise
        """
        now = datetime.now()
        batch_start = time(self.config.batch_processing_hour, 0)
        batch_end = time(self.config.batch_processing_hour + 2, 0)

        if batch_start < batch_end:
            return batch_start <= now.time() < batch_end
        else:
            # Handles case where window crosses midnight
            return now.time() >= batch_start or now.time() < batch_end

    async def shutdown(self) -> None:
        """Gracefully shutdown worker."""
        try:
            logger.info("Shutting down worker...")
            self.running = False

            # Close database
            if self.db_engine:
                await self.db_engine.dispose()

            # Close Redis
            if self.redis_manager:
                await self.redis_manager.disconnect()

            # Close bot session
            if self.bot:
                await self.bot.session.close()

            logger.info("Worker shutdown complete")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")


async def main() -> None:
    """Main entry point."""
    try:
        config = WorkerConfig()
        worker = SummaryWorker(config)

        # Initialize
        if not await worker.initialize():
            logger.error("Failed to initialize worker")
            return

        # Run
        await worker.run()

    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
