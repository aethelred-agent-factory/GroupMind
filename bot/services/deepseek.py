"""
DeepSeek API service for intelligent summarization and analysis.

This module provides:
- Async HTTP client for DeepSeek API
- Retry logic with exponential backoff (3 retries)
- Rate limiting to respect API quotas
- Error handling for API failures
- Response validation with Pydantic
- Fallback to simple summary if API fails
- Context window management (128K token limit)
"""

import logging
import asyncio
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from enum import Enum

import httpx
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class SummaryType(str, Enum):
    """Type of summary to generate."""
    CONCISE = "concise"
    DETAILED = "detailed"
    BULLET_POINTS = "bullet_points"


class Message(BaseModel):
    """Message data model."""
    user: str
    text: str
    timestamp: Optional[str] = None

    class Config:
        """Pydantic config."""
        str_strip_whitespace = True


class DeepSeekResponse(BaseModel):
    """Response from DeepSeek API."""
    summary: str = Field(..., min_length=1, max_length=10000)
    key_topics: List[str] = Field(default_factory=list)
    sentiment: Optional[str] = None
    action_items: List[str] = Field(default_factory=list)

    @validator("key_topics", pre=True, always=True)
    def ensure_key_topics(cls, v):
        """Ensure key_topics is a list."""
        if isinstance(v, str):
            return [v]
        return v or []

    @validator("action_items", pre=True, always=True)
    def ensure_action_items(cls, v):
        """Ensure action_items is a list."""
        if isinstance(v, str):
            return [v]
        return v or []


class SimpleSummary(BaseModel):
    """Fallback simple summary model."""
    summary: str
    key_topics: List[str] = Field(default_factory=list)
    sentiment: Optional[str] = None
    action_items: List[str] = Field(default_factory=list)


class RateLimiter:
    """Rate limiter for API requests."""

    def __init__(
        self,
        requests_per_minute: int = 10,
        requests_per_hour: int = 100,
    ):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Max requests per minute
            requests_per_hour: Max requests per hour
        """
        self.rpm = requests_per_minute
        self.rph = requests_per_hour
        self.request_times: List[datetime] = []

    async def wait_if_needed(self) -> None:
        """Wait if rate limit would be exceeded."""
        now = datetime.now()
        one_minute_ago = now - timedelta(minutes=1)
        one_hour_ago = now - timedelta(hours=1)

        # Remove old entries
        self.request_times = [
            t for t in self.request_times if t > one_hour_ago
        ]

        # Check hour limit
        if len(self.request_times) >= self.rph:
            sleep_time = (
                self.request_times[0] + timedelta(hours=1) - now
            ).total_seconds()
            if sleep_time > 0:
                logger.warning(f"Rate limit: sleeping {sleep_time:.1f}s")
                await asyncio.sleep(sleep_time + 1)
                self.request_times = []
            return

        # Check minute limit
        recent_requests = [
            t for t in self.request_times if t > one_minute_ago
        ]
        if len(recent_requests) >= self.rpm:
            sleep_time = (
                recent_requests[0] + timedelta(minutes=1) - now
            ).total_seconds()
            if sleep_time > 0:
                logger.debug(f"Rate limit: sleeping {sleep_time:.1f}s")
                await asyncio.sleep(sleep_time + 0.1)

        # Record this request
        self.request_times.append(now)


class TokenCounter:
    """Estimates token count for text."""

    # Rough estimation: 1 token ≈ 4 characters for English
    CHARS_PER_TOKEN = 4
    MAX_TOKENS = 128000
    # Reserve tokens for response (estimate)
    RESPONSE_TOKENS = 4000

    @classmethod
    def count_tokens(cls, text: str) -> int:
        """
        Estimate token count.

        Args:
            text: Text to count

        Returns:
            Estimated token count
        """
        return len(text) // cls.CHARS_PER_TOKEN

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """
        Estimate token count (alias for count_tokens).

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return cls.count_tokens(text)

    @classmethod
    def get_available_tokens(cls) -> int:
        """Get available tokens after reserve."""
        return cls.MAX_TOKENS - cls.RESPONSE_TOKENS

    @classmethod
    def trim_context(cls, text: str, max_tokens: Optional[int] = None) -> str:
        """
        Trim text to fit within token limit.

        Args:
            text: Text to trim
            max_tokens: Maximum tokens (default: available tokens)

        Returns:
            Trimmed text
        """
        max_tokens = max_tokens or cls.get_available_tokens()
        max_chars = max_tokens * cls.CHARS_PER_TOKEN

        if len(text) <= max_chars:
            return text

        logger.warning(
            f"Context exceeds token limit: {cls.count_tokens(text)}/{max_tokens} tokens"
        )
        # Trim and add ellipsis
        return text[:max_chars - 100] + "\n...[context trimmed]"


class DeepSeekClient:
    """Async HTTP client for DeepSeek API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout: int = 120,
        max_retries: int = 3,
        requests_per_minute: int = 10,
    ):
        """
        Initialize DeepSeek client.

        Args:
            api_key: DeepSeek API key
            base_url: API base URL
            model: Model to use
            timeout: Request timeout in seconds
            max_retries: Maximum retries with exponential backoff
            requests_per_minute: Rate limit
        """
        self.api_key = api_key
        base_url = base_url.rstrip("/")
        # Ensure /v1 suffix
        if not base_url.endswith("/v1"):
            base_url = base_url + "/v1"
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limiter = RateLimiter(requests_per_minute=requests_per_minute)
        self.client: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> None:
        """Initialize async HTTP client."""
        try:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            logger.info("DeepSeek client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize DeepSeek client: {e}")
            raise

    async def close(self) -> None:
        """Close HTTP client."""
        if self.client:
            await self.client.aclose()
            logger.info("DeepSeek client closed")

    async def _make_request(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
    ) -> Optional[str]:
        """
        Make API request with retry logic.

        Args:
            messages: Message list for API
            temperature: Temperature for generation

        Returns:
            Generated text or None on failure
        """
        if not self.client:
            raise RuntimeError("Client not initialized")

        # Wait for rate limit
        await self.rate_limiter.wait_if_needed()

        backoff_base = 2
        last_error = None

        for attempt in range(self.max_retries):
            try:
                logger.debug(
                    f"DeepSeek API request (attempt {attempt + 1}/{self.max_retries})"
                )

                response = await self.client.post(
                    "/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": 4000,
                    },
                )

                # Check for successful response
                if response.status_code == 200:
                    data = response.json()
                    if data.get("choices") and len(data["choices"]) > 0:
                        content = data["choices"][0].get("message", {}).get("content", "")
                        logger.debug("DeepSeek API request successful")
                        return content
                    else:
                        logger.error("Invalid response structure from API")
                        return None

                # Handle rate limiting
                elif response.status_code == 429:
                    retry_after = int(response.headers.get("retry-after", 60))
                    logger.warning(f"Rate limited by API, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue

                # Handle other errors
                elif response.status_code >= 500:
                    last_error = f"Server error: {response.status_code}"
                    logger.warning(f"Server error: {response.status_code}")
                    if attempt < self.max_retries - 1:
                        wait_time = backoff_base ** attempt
                        logger.debug(f"Retrying after {wait_time}s")
                        await asyncio.sleep(wait_time)
                        continue
                else:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", "Unknown error")
                    logger.error(f"API error: {response.status_code} - {error_msg}")
                    return None

            except asyncio.TimeoutError:
                last_error = "Request timeout"
                logger.warning(f"Request timeout (attempt {attempt + 1})")
                if attempt < self.max_retries - 1:
                    wait_time = backoff_base ** attempt
                    await asyncio.sleep(wait_time)
                    continue
            except httpx.RequestError as e:
                last_error = str(e)
                logger.warning(f"Request error: {e} (attempt {attempt + 1})")
                if attempt < self.max_retries - 1:
                    wait_time = backoff_base ** attempt
                    await asyncio.sleep(wait_time)
                    continue
            except Exception as e:
                last_error = str(e)
                logger.error(f"Unexpected error: {e}")
                return None

        logger.error(f"Failed after {self.max_retries} retries: {last_error}")
        return None

    async def summarize_messages(
        self,
        messages: List[Message],
        summary_type: SummaryType = SummaryType.CONCISE,
    ) -> Optional[DeepSeekResponse]:
        """
        Summarize messages using DeepSeek.

        Args:
            messages: List of messages to summarize
            summary_type: Type of summary to generate

        Returns:
            DeepSeekResponse or None on failure
        """
        try:
            if not messages:
                logger.warning("Empty message list for summarization")
                return None

            # Format messages for context
            context = self._format_messages_context(messages)

            # Trim context to fit token limit
            context = TokenCounter.trim_context(context)

            # Build prompt
            prompt = self._build_summarization_prompt(context, summary_type)

            # Make API request
            response_text = await self._make_request(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert at summarizing group conversations. "
                            "Provide clear, concise summaries with key topics and actionable insights."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,  # Lower temperature for consistency
            )

            if not response_text:
                return None

            # Parse and validate response
            try:
                # Try to extract JSON from response
                import json
                import re

                # Look for JSON block in response
                json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    response_data = json.loads(json_str)
                else:
                    # Fallback: create response from text
                    response_data = {
                        "summary": response_text,
                        "key_topics": [],
                        "sentiment": "neutral",
                        "action_items": [],
                    }

                response = DeepSeekResponse(**response_data)
                logger.info("Successfully generated summary from DeepSeek")
                return response

            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse response JSON: {e}")
                # Return response with raw text as summary
                return DeepSeekResponse(
                    summary=response_text,
                    key_topics=[],
                    sentiment="neutral",
                    action_items=[],
                )

        except Exception as e:
            logger.error(f"Error in summarize_messages: {e}")
            return None

    async def analyze_sentiment(self, text: str) -> Optional[str]:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze

        Returns:
            Sentiment classification or None
        """
        try:
            response_text = await self._make_request(
                messages=[
                    {
                        "role": "system",
                        "content": "Classify sentiment as: positive, negative, or neutral.",
                    },
                    {"role": "user", "content": f"Analyze this text: {text}"},
                ],
                temperature=0.0,
            )

            if response_text:
                sentiment = response_text.lower()
                if "positive" in sentiment:
                    return "positive"
                elif "negative" in sentiment:
                    return "negative"
                else:
                    return "neutral"
            return None

        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return None

    def _format_messages_context(self, messages: List[Message]) -> str:
        """Format messages into context string."""
        lines = []
        for msg in messages:
            timestamp = msg.timestamp or "unknown time"
            user = msg.user or "Unknown"
            lines.append(f"[{timestamp}] {user}: {msg.text}")
        return "\n".join(lines)

    def _build_summarization_prompt(
        self,
        context: str,
        summary_type: SummaryType,
    ) -> str:
        """Build summarization prompt based on type."""
        prompts = {
            SummaryType.CONCISE: (
                "Provide a brief summary (2-3 sentences) of the main discussion topics.\n"
                "Format your response as JSON with keys: summary, key_topics, sentiment, action_items"
            ),
            SummaryType.DETAILED: (
                "Provide a detailed summary covering all main discussion points and decisions.\n"
                "Format your response as JSON with keys: summary, key_topics, sentiment, action_items"
            ),
            SummaryType.BULLET_POINTS: (
                "Provide a bullet-point summary of the conversation.\n"
                "Format your response as JSON with keys: summary (as bullet points), key_topics, sentiment, action_items"
            ),
        }

        base_prompt = prompts.get(
            summary_type,
            prompts[SummaryType.CONCISE],
        )

        return f"""Please summarize this group conversation:

{context}

{base_prompt}"""


class SimpleSummaryGenerator:
    """Generate simple fallback summaries without API."""

    def generate(self, text: str) -> str:
        """
        Generate simple summary from text.

        Args:
            text: Text to summarize

        Returns:
            Summary string
        """
        if not text:
            return "No content to summarize."

        # Split into sentences
        sentences = [s.strip() for s in text.split('.') if s.strip()]

        if not sentences:
            return text[:200]  # Return first 200 chars

        # For a simple generator, just return a basic summary
        key_sentences = sentences[:3]  # Take first 3 sentences
        summary = ". ".join(key_sentences)

        if len(summary) > 500:
            summary = summary[:500] + "..."

        return summary

    @staticmethod
    def generate_summary(messages: List[Message]) -> SimpleSummary:
        """
        Generate simple summary from messages.

        Args:
            messages: List of messages

        Returns:
            SimpleSummary object
        """
        if not messages:
            return SimpleSummary(
                summary="No messages to summarize.",
                key_topics=[],
                sentiment="neutral",
                action_items=[],
            )

        # Extract unique users
        users = list(set(msg.user for msg in messages if msg.user))

        # Count messages per user
        user_counts = {}
        for msg in messages:
            if msg.user:
                user_counts[msg.user] = user_counts.get(msg.user, 0) + 1

        # Sort by most active
        top_users = sorted(
            user_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:3]

        # Extract key topics (simplified - just look for common words)
        words = []
        for msg in messages:
            words.extend(msg.text.lower().split())

        # Filter common words
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "is", "are", "was", "were", "be",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "must", "can",
        }

        key_topics = [
            word for word in set(words)
            if len(word) > 3 and word not in stop_words
        ][:5]

        summary = (
            f"Group conversation with {len(users)} participants. "
            f"Most active: {', '.join([name for name, _ in top_users])}. "
            f"Total messages: {len(messages)}."
        )

        return SimpleSummary(
            summary=summary,
            key_topics=key_topics,
            sentiment="neutral",
            action_items=[],
        )
