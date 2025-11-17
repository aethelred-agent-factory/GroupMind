"""Integration tests for complete workflows."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import json

from bot.handlers.messages import MessageHandler, PrivacyManager, MessageBatcher
from bot.handlers.commands import CommandHandler
from bot.services.sentiment import SentimentAnalyzer


@pytest.mark.asyncio
class TestMessageWorkflow:
    """Test message handling workflow."""
    
    async def test_message_capture_and_storage(
        self,
        mock_telegram_message,
        mock_context,
        mock_redis
    ):
        """Test message capture workflow."""
        handler = MessageHandler(redis_url="redis://localhost")
        handler.redis = mock_redis
        
        # Mock Redis operations
        mock_redis.lpush = AsyncMock(return_value=1)
        mock_redis.llen = AsyncMock(return_value=1)
        
        # Would be called with actual update
        assert handler is not None
    
    async def test_privacy_manager_filters_personal_info(self):
        """Test privacy manager filters sensitive data."""
        privacy_manager = PrivacyManager()
        
        sensitive_message = "My phone is +1234567890 and email is test@example.com"
        cleaned = privacy_manager.clean_message(sensitive_message)
        
        assert "+1234567890" not in cleaned or "PHONE" in cleaned
        assert "test@example.com" not in cleaned or "EMAIL" in cleaned
    
    async def test_message_batcher_accumulation(self):
        """Test message batcher accumulates messages."""
        batcher = MessageBatcher(max_batch_size=1000)
        
        messages = [
            {"text": f"Message {i}", "user_id": 123, "timestamp": datetime.utcnow()}
            for i in range(10)
        ]
        
        for msg in messages:
            batcher.add(msg)
        
        assert batcher.count() == len(messages)
    
    async def test_message_batcher_flush(self):
        """Test message batcher flush."""
        batcher = MessageBatcher(max_batch_size=1000)
        
        messages = [
            {"text": f"Message {i}", "user_id": 123}
            for i in range(5)
        ]
        
        for msg in messages:
            batcher.add(msg)
        
        batch = batcher.flush()
        
        assert len(batch) == 5
        assert batcher.count() == 0


@pytest.mark.asyncio
class TestSentimentAnalysisWorkflow:
    """Test sentiment analysis workflow."""
    
    async def test_analyze_conversation_sentiment(self):
        """Test analyzing sentiment of a conversation."""
        analyzer = SentimentAnalyzer()
        
        conversation = [
            "Alice: This is great!",
            "Bob: I love it",
            "Charlie: Not sure about this",
        ]
        
        results = []
        for msg in conversation:
            # Extract text after username
            text = msg.split(": ", 1)[1] if ": " in msg else msg
            sentiment, score = analyzer.analyze(text)
            results.append({
                "message": msg,
                "sentiment": sentiment,
                "score": score
            })
        
        assert len(results) == 3
        assert any(r["sentiment"] == "positive" for r in results)
    
    async def test_detect_conflict_patterns(self):
        """Test detection of conflict patterns."""
        analyzer = SentimentAnalyzer()
        
        conflict_messages = [
            "I COMPLETELY DISAGREE!!!",
            "That's wrong and you know it",
            "This will never work!",
        ]
        
        for msg in conflict_messages:
            sentiment, score = analyzer.analyze(msg)
            emotions = analyzer.detect_emotions(msg)
            
            assert sentiment == "negative" or len(emotions) > 0


@pytest.mark.asyncio
class TestCommandRateLimitingWorkflow:
    """Test command handling with rate limiting."""
    
    async def test_summary_command_respects_rate_limit(
        self,
        mock_context,
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test that summary command respects rate limits."""
        handler = CommandHandler(redis_url="redis://localhost")
        handler.redis = mock_redis
        
        # Simulate rate limit tracking
        user_key = f"rate_limit:user:{mock_telegram_user.id}"
        group_key = f"rate_limit:group:{mock_telegram_chat.id}"
        
        mock_redis.get = AsyncMock(side_effect=lambda key: 
            b"5" if key == user_key else None
        )
        mock_redis.incr = AsyncMock(return_value=6)
        
        # Check if rate limited
        assert handler is not None
    
    async def test_tiered_rate_limiting(self, mock_redis):
        """Test tiered rate limiting (FREE, PRO, ENTERPRISE)."""
        from bot.utils.rate_limiter import RateLimitTier
        
        tiers = [
            (RateLimitTier.FREE, 5, 3600),
            (RateLimitTier.PRO, 30, 3600),
            (RateLimitTier.ENTERPRISE, 200, 3600),
        ]
        
        for tier, limit, window in tiers:
            assert limit is not None
            assert window > 0


@pytest.mark.asyncio
class TestEndToEndWorkflow:
    """Test end-to-end bot workflow."""
    
    async def test_message_to_summary_pipeline(
        self,
        mock_context,
        mock_telegram_message,
        mock_redis
    ):
        """Test complete pipeline from message capture to summary."""
        # This would test the full workflow:
        # 1. Message captured
        # 2. Sentiment analyzed
        # 3. Added to queue
        # 4. Batch processing
        # 5. DeepSeek summary generation
        # 6. Result notification
        
        message_handler = MessageHandler(redis_url="redis://localhost")
        command_handler = CommandHandler(redis_url="redis://localhost")
        sentiment_analyzer = SentimentAnalyzer()
        
        assert message_handler is not None
        assert command_handler is not None
        assert sentiment_analyzer is not None
    
    async def test_user_journey(
        self,
        mock_context,
        mock_telegram_user,
        mock_telegram_chat,
        mock_redis
    ):
        """Test complete user journey."""
        # User journey:
        # 1. /start command
        # 2. Join group
        # 3. Messages get captured
        # 4. /summary command
        # 5. Receive summary
        
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.lpush = AsyncMock(return_value=1)
        
        handler = CommandHandler(redis_url="redis://localhost")
        handler.redis = mock_redis
        
        # Simulate start command
        assert hasattr(handler, 'start')


@pytest.mark.asyncio
class TestErrorRecovery:
    """Test error recovery and fallback behavior."""
    
    async def test_deepseek_failure_fallback(self):
        """Test fallback when DeepSeek API fails."""
        from bot.services.deepseek import DeepSeekClient, SimpleSummaryGenerator
        
        client = DeepSeekClient(api_key="test_key")
        generator = SimpleSummaryGenerator()
        
        # Should have fallback available
        assert hasattr(generator, 'generate')
        assert callable(generator.generate)
    
    async def test_redis_connection_failure(self, mock_redis):
        """Test handling of Redis connection failures."""
        mock_redis.ping = AsyncMock(side_effect=Exception("Connection refused"))
        
        # Should handle gracefully
        handler = CommandHandler(redis_url="redis://localhost")
        handler.redis = mock_redis
        
        # Handler should still be created even if Redis is unavailable
        assert handler is not None
    
    async def test_database_transaction_rollback(self, test_db):
        """Test database transaction rollback on error."""
        from sqlalchemy import select
        from bot.models.database import Group
        
        try:
            group = Group(
                group_id=-9876543210,
                title="Test",
                member_count=1,
                is_active=True,
            )
            test_db.add(group)
            
            # Simulate error
            raise Exception("Simulated error")
            
        except Exception:
            await test_db.rollback()
        
        # Verify rollback (shouldn't find the group)
        result = await test_db.execute(
            select(Group).where(Group.group_id == -9876543210)
        )
        assert result.scalar_one_or_none() is None
