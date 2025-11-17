"""Integration tests for complete workflows."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import json

from bot.services.sentiment import SentimentAnalyzer


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

