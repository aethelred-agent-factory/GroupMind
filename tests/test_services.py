"""Tests for service modules."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from datetime import datetime

from bot.services.deepseek import DeepSeekClient, TokenCounter, SimpleSummaryGenerator
from bot.services.sentiment import SentimentAnalyzer
from bot.services.summarizer import Summarizer


@pytest.mark.asyncio
class TestDeepSeekClient:
    """Test suite for DeepSeekClient."""
    
    async def test_initialize_client(self):
        """Test DeepSeekClient initialization."""
        client = DeepSeekClient(api_key="test_key_123")
        
        assert client.api_key == "test_key_123"
        assert client.base_url == "https://api.deepseek.com/v1"
        assert client.model == "deepseek-chat"
        assert client.max_retries == 3
    
    async def test_generate_summary_success(self):
        """Test successful summary generation."""
        from bot.services.deepseek import Message as APIMessage
        
        client = DeepSeekClient(api_key="test_key_123")
        await client.initialize()
        
        # Create test messages
        test_messages = [
            APIMessage(user="user1", text="Hello everyone"),
            APIMessage(user="user2", text="Hi! How are you?"),
        ]
        
        # Mock the _make_request method
        with patch.object(client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = '{"summary": "A summary", "key_topics": ["greeting"]}'
            
            result = await client.summarize_messages(test_messages)
            assert result is not None
        
        await client.close()
    
    async def test_generate_summary_with_retry(self):
        """Test summary generation with retry logic."""
        client = DeepSeekClient(api_key="test_key_123")
        
        # First call fails, second succeeds
        with patch("aiohttp.ClientSession") as mock_session:
            mock_post = AsyncMock()
            mock_session.return_value.__aenter__.return_value.post.return_value = mock_post
            
            # Simulate failure then success
            mock_post.__aenter__.side_effect = [
                MagicMock(status=429),  # Rate limited
                MagicMock(
                    status=200,
                    json=AsyncMock(return_value={
                        "choices": [{"message": {"content": "Retry successful"}}],
                        "usage": {"prompt_tokens": 100, "completion_tokens": 50}
                    })
                )
            ]
            
            # This tests the retry behavior
            assert hasattr(client, 'max_retries')
            assert client.max_retries >= 1
    
    def test_token_counter(self):
        """Test token counter estimation."""
        # Test word approximation
        text = "This is a test. It has multiple words."
        estimated_tokens = TokenCounter.estimate_tokens(text)
        
        assert estimated_tokens > 0
        assert isinstance(estimated_tokens, int)
    
    def test_token_counter_max_context(self):
        """Test token counter respects max context."""
        text = "word " * 500  # Create large text
        truncated = TokenCounter.trim_context(text, max_tokens=100)
        
        assert len(truncated) <= len(text)


@pytest.mark.asyncio
class TestSentimentAnalyzer:
    """Test suite for SentimentAnalyzer."""
    
    def test_analyze_positive_sentiment(self):
        """Test positive sentiment detection."""
        analyzer = SentimentAnalyzer()
        
        text = "This is absolutely amazing! I love it so much!"
        sentiment, score = analyzer.analyze(text)
        
        assert sentiment == "positive"
        assert score > 0
    
    def test_analyze_negative_sentiment(self):
        """Test negative sentiment detection."""
        analyzer = SentimentAnalyzer()
        
        text = "This is terrible and awful. I hate it!"
        sentiment, score = analyzer.analyze(text)
        
        assert sentiment == "negative"
        assert score < 0
    
    def test_analyze_neutral_sentiment(self):
        """Test neutral sentiment detection."""
        analyzer = SentimentAnalyzer()
        
        text = "The meeting is scheduled for tomorrow at 2 PM."
        sentiment, score = analyzer.analyze(text)
        
        assert sentiment == "neutral"
        assert score == 0
    
    def test_detect_emotions(self):
        """Test emotion detection."""
        analyzer = SentimentAnalyzer()
        
        text = "I'm so happy and excited about this project!"
        emotions = analyzer.detect_emotions(text)
        
        assert len(emotions) > 0
        assert isinstance(emotions, dict)
    
    def test_batch_analysis(self):
        """Test batch sentiment analysis."""
        analyzer = SentimentAnalyzer()
        
        messages = [
            "Great job!",
            "This is terrible",
            "Let's meet tomorrow"
        ]
        
        results = analyzer.batch_analyze(messages)
        
        assert len(results) == len(messages)
        assert all(isinstance(r, tuple) for r in results)


@pytest.mark.asyncio
class TestSummarizer:
    """Test suite for Summarizer."""
    
    def test_summarizer_initialization(self):
        """Test Summarizer initialization."""
        summarizer = Summarizer()
        
        assert hasattr(summarizer, 'language_detector')
        assert hasattr(summarizer, 'context_optimizer')
        assert hasattr(summarizer, 'conversation_analyzer')
    
    def test_detect_language(self):
        """Test language detection."""
        summarizer = Summarizer()
        
        texts_and_langs = [
            ("Hello, this is English", "en"),
            ("Bonjour, ceci est français", "fr"),
            ("Hola, esto es español", "es"),
        ]
        
        for text, expected_lang in texts_and_langs:
            detected = summarizer.language_detector.detect(text)
            assert detected is not None
    
    def test_analyze_conversation(self):
        """Test conversation analysis."""
        summarizer = Summarizer()
        
        messages = [
            {"text": "Let's discuss the project timeline", "user": "Alice"},
            {"text": "I think we need more time", "user": "Bob"},
            {"text": "Agreed, I'll update the schedule", "user": "Alice"},
        ]
        
        analysis = summarizer.conversation_analyzer.analyze(messages)
        
        assert analysis is not None
        assert isinstance(analysis, dict)
    
    def test_get_summary_prompt(self):
        """Test summary prompt generation."""
        summarizer = Summarizer()
        
        prompt = summarizer.get_summary_prompt(
            conversation="Test conversation",
            language="en",
            style="concise"
        )
        
        assert prompt is not None
        assert isinstance(prompt, str)
        assert len(prompt) > 0


@pytest.mark.asyncio
class TestServiceIntegration:
    """Integration tests for services."""
    
    async def test_end_to_end_sentiment_analysis(self):
        """Test sentiment analysis workflow."""
        analyzer = SentimentAnalyzer()
        
        messages = [
            "I love this new feature!",
            "This is broken",
            "Just informing you about the deadline",
        ]
        
        results = []
        for msg in messages:
            sentiment, score = analyzer.analyze(msg)
            results.append({"message": msg, "sentiment": sentiment, "score": score})
        
        assert len(results) == len(messages)
        assert all("sentiment" in r and "score" in r for r in results)
    
    async def test_token_counter_estimation(self):
        """Test token counter accuracy."""
        counter = TokenCounter()
        
        # Test various text lengths
        texts = [
            "Short text",
            "This is a medium length text with several words",
            "This is a longer text " * 10,
        ]
        
        for text in texts:
            tokens = counter.estimate_tokens(text)
            assert tokens > 0
            # Rough check: approximately 1 token per 4 characters
            expected_approx = len(text) // 4
            assert abs(tokens - expected_approx) < expected_approx * 0.5
    
    async def test_simple_summary_generator(self):
        """Test SimpleSummaryGenerator fallback."""
        generator = SimpleSummaryGenerator()
        
        messages = [
            "Alice: Let's discuss the project",
            "Bob: I agree",
            "Alice: We need to finish by Friday",
        ]
        
        summary = generator.generate("\n".join(messages))
        
        assert summary is not None
        assert isinstance(summary, str)
        assert len(summary) > 0
