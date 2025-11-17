"""
Sentiment analysis service for GroupMind.

This module provides:
- Basic sentiment analysis (positive/neutral/negative/conflict)
- Emotional tone detection from message patterns
- Conflict/disagreement identification
- Keyword-based fallback analysis
- Sentiment scoring and emotion classification
"""

import logging
import re
from typing import Optional, Dict, List, Tuple
from enum import Enum
from dataclasses import dataclass

from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class Sentiment(str, Enum):
    """Sentiment classification."""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    CONFLICT = "conflict"
    MIXED = "mixed"


class Emotion(str, Enum):
    """Emotion classification."""
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    NEUTRAL = "neutral"


@dataclass
class SentimentScore:
    """Sentiment analysis result."""
    sentiment: Sentiment
    dominant_emotion: Emotion
    score: float = Field(default=0.5, ge=-1.0, le=1.0)  # -1 to 1
    emotions: Dict[str, float] = None
    keywords: List[str] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "sentiment": self.sentiment.value,
            "score": self.score,
            "dominant_emotion": self.dominant_emotion.value,
            "emotions": self.emotions,
            "keywords": self.keywords,
            "confidence": self.confidence,
        }


class SentimentKeywords:
    """Keywords for sentiment analysis."""

    POSITIVE_WORDS = {
        # Happiness/Joy
        "happy", "joy", "joyful", "wonderful", "amazing", "awesome", "great",
        "fantastic", "excellent", "brilliant", "love", "adore", "perfect",
        "beautiful", "lovely", "good", "nice", "cool", "super",
        # Agreement
        "agree", "agreement", "yes", "absolutely", "definitely", "exactly",
        "right", "correct", "well done", "congratulations", "bravo",
        # Success
        "success", "successful", "succeeded", "achieved", "accomplished",
        "completed", "finished", "done", "solved", "resolved",
        # Hope/Optimism
        "hope", "hopeful", "optimistic", "promising", "possibility", "opportunity",
        "bright", "positive", "good news", "exciting",
    }

    NEGATIVE_WORDS = {
        # Sadness/Pain
        "sad", "sadness", "unhappy", "miserable", "depressed", "down",
        "upset", "hurt", "pain", "painful", "terrible", "awful", "horrible",
        "bad", "poor", "weak", "fail", "failure", "disappointed",
        # Anger/Frustration
        "angry", "anger", "furious", "rage", "mad", "frustrated", "frustration",
        "annoyed", "annoying", "irritated", "irritating", "hate", "despise",
        # Concern
        "worried", "worry", "concerned", "concern", "anxious", "anxiety",
        "afraid", "fear", "scared", "scary", "dangerous",
        # Dislike
        "dislike", "disagree", "wrong", "incorrect", "bad", "problem", "issue",
        "broken", "error", "fault", "blame",
    }

    CONFLICT_WORDS = {
        # Disagreement
        "disagree", "disagreement", "argument", "debate", "conflict", "dispute",
        "versus", "vs", "against", "oppose", "opposition", "contrary",
        # Blame/Accusation
        "blame", "fault", "wrong", "your fault", "your problem",
        "accusation", "accuse", "guilty",
        # Intensity markers for conflict
        "completely", "totally", "absolutely", "never", "always",
        "you never", "you always", "always wrong", "always right",
        # Sarcasm/Passive aggression
        "sure", "right", "whatever", "fine", "okay then", "obviously",
    }

    EMOTION_KEYWORDS = {
        Emotion.JOY: [
            "happy", "joy", "laugh", "smile", "haha", "hehe", "fun",
            "amazing", "wonderful", "love", "awesome", "great",
        ],
        Emotion.SADNESS: [
            "sad", "cry", "tears", "upset", "depressed", "sorry", "unhappy",
            "disappointed", "down", "hurt", "pain",
        ],
        Emotion.ANGER: [
            "angry", "mad", "furious", "rage", "hate", "frustrated",
            "annoyed", "irritated", "upset", "angry", "aggressive",
        ],
        Emotion.FEAR: [
            "fear", "afraid", "scared", "worry", "anxious", "nervous",
            "concerned", "concerned", "dread", "apprehensive",
        ],
        Emotion.SURPRISE: [
            "surprise", "shocked", "wow", "amazing", "unexpected",
            "sudden", "astonished", "stunned", "wow", "wait what",
        ],
        Emotion.DISGUST: [
            "disgusting", "gross", "nasty", "ugly", "revolting", "yuck",
            "awful", "terrible", "horrible", "disgusted",
        ],
        Emotion.NEUTRAL: [
            "okay", "fine", "alright", "sure", "got it", "understood",
            "noted", "thanks", "thanks for info", "good to know",
        ],
    }

    INTENSIFIERS = {
        "very", "extremely", "incredibly", "absolutely", "totally",
        "completely", "really", "so", "super", "quite", "rather",
    }

    NEGATIONS = {
        "not", "no", "don't", "doesn't", "didn't", "won't", "can't",
        "couldn't", "wouldn't", "shouldn't", "haven't", "hasn't", "hadn't",
    }


class PatternDetector:
    """Detects sentiment patterns in text."""

    @staticmethod
    def detect_all_caps(text: str) -> bool:
        """Detect if text is written in ALL CAPS."""
        if len(text) < 3:
            return False
        letters = [c for c in text if c.isalpha()]
        if not letters:
            return False
        caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        return caps_ratio > 0.8

    @staticmethod
    def detect_repeated_punctuation(text: str) -> Tuple[bool, str]:
        """
        Detect repeated punctuation (!!! or ???).

        Returns:
            Tuple of (detected, punctuation_type)
        """
        # Multiple exclamation marks
        if re.search(r'!{2,}', text):
            return True, "exclamation"
        # Multiple question marks
        if re.search(r'\?{2,}', text):
            return True, "question"
        return False, ""

    @staticmethod
    def detect_ellipsis(text: str) -> bool:
        """Detect ellipsis (...) which often indicates trailing off or concern."""
        return bool(re.search(r'\.{2,}', text))

    @staticmethod
    def detect_sarcasm_markers(text: str) -> bool:
        """Detect potential sarcasm markers."""
        sarcasm_patterns = [
            r'/s\b',  # /s tag
            r'yeah\s+right',
            r'sure\s+(?:buddy|pal)',
            r'oh\s+(?:please|come\s+on)',
        ]
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in sarcasm_patterns)

    @staticmethod
    def detect_question_tone(text: str) -> bool:
        """Detect if text is primarily questioning."""
        questions = len(re.findall(r'\?', text))
        total_sentences = len(re.findall(r'[.!?]', text)) + 1
        return questions / total_sentences > 0.5 if total_sentences > 0 else False

    @staticmethod
    def detect_negation_reversal(text: str) -> bool:
        """
        Detect negation that might reverse sentiment.

        Example: "not good" = negative, despite "good" being positive
        """
        negations = SentimentKeywords.NEGATIONS
        words = text.lower().split()

        for i, word in enumerate(words):
            if word in negations and i + 1 < len(words):
                next_word = words[i + 1]
                # Check if next word is sentiment word
                if (next_word in SentimentKeywords.POSITIVE_WORDS or
                    next_word in SentimentKeywords.NEGATIVE_WORDS):
                    return True
        return False


class EmotionAnalyzer:
    """Analyzes emotions in text."""

    @staticmethod
    def detect_emotions(text: str) -> Dict[Emotion, float]:
        """
        Detect emotions in text.

        Args:
            text: Text to analyze

        Returns:
            Dictionary mapping emotions to scores (0-1)
        """
        text_lower = text.lower()
        emotions = {}

        for emotion, keywords in SentimentKeywords.EMOTION_KEYWORDS.items():
            score = 0.0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 1.0

            # Normalize score
            if keywords:
                score = min(score / len(keywords), 1.0)

            emotions[emotion] = score

        return emotions

    @staticmethod
    def get_dominant_emotion(emotions: Dict[Emotion, float]) -> Emotion:
        """
        Get dominant emotion from scores.

        Args:
            emotions: Dictionary of emotion scores

        Returns:
            Dominant emotion
        """
        if not emotions or all(v == 0 for v in emotions.values()):
            return Emotion.NEUTRAL

        return max(emotions.items(), key=lambda x: x[1])[0]


class ConflictDetector:
    """Detects conflicts and disagreements."""

    @staticmethod
    def detect_direct_disagreement(text: str) -> bool:
        """Detect direct disagreement markers."""
        disagreement_patterns = [
            r'\byou\s+(?:are\s+)?wrong',
            r'\bi\s+disagree',
            r'\bthat[\'s]*s\s+(?:wrong|false|incorrect)',
            r'\byou\s+(?:don\'t|do not)\s+understand',
            r'\bthat\s+(?:doesn\'t|does not)\s+make\s+sense',
        ]
        return any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in disagreement_patterns
        )

    @staticmethod
    def detect_blame(text: str) -> bool:
        """Detect blame or accusation."""
        blame_patterns = [
            r'\byour\s+(?:fault|problem|mistake)',
            r'\byou\s+(?:caused|made|broke)',
            r'\byou\s+always',
            r'\byou\s+never',
            r'\byou\s+should\s+have',
        ]
        return any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in blame_patterns
        )

    @staticmethod
    def detect_passive_aggression(text: str) -> bool:
        """Detect passive-aggressive tone."""
        passive_markers = [
            r'\bfine\b',
            r'\bokay\s+then\b',
            r'\bwhatever\b',
            r'\bif\s+you\s+say\s+so\b',
            r'\bsure\s+(?:buddy|pal)\b',
        ]
        # Only count as passive aggression if in certain context
        all_caps = PatternDetector.detect_all_caps(text)
        repeated_punct, _ = PatternDetector.detect_repeated_punctuation(text)

        passive_found = any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in passive_markers
        )

        return passive_found and (all_caps or repeated_punct)


class SentimentAnalyzer:
    """Main sentiment analyzer."""

    def __init__(self):
        """Initialize sentiment analyzer."""
        self.emotion_analyzer = EmotionAnalyzer()
        self.conflict_detector = ConflictDetector()
        self.pattern_detector = PatternDetector()

    def analyze(self, text: str) -> Tuple[str, float]:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze

        Returns:
            Tuple of (sentiment_string, score)
        """
        if not text or len(text.strip()) == 0:
            return Sentiment.NEUTRAL.value, 0.0

        text_lower = text.lower()

        # Detect conflict first
        conflict_score = self._detect_conflict_level(text_lower)

        if conflict_score > 0.6:
            result = self._create_conflict_score(text_lower)
            return result.sentiment.value, result.score

        # Analyze sentiment
        sentiment, score, keywords = self._analyze_sentiment(text_lower)

        # Detect emotions
        emotions = self.emotion_analyzer.detect_emotions(text_lower)
        dominant_emotion = self.emotion_analyzer.get_dominant_emotion(emotions)

        # Calculate confidence
        confidence = self._calculate_confidence(text, keywords, emotions)

        logger.debug(
            f"Sentiment analysis: {sentiment.value} (score={score:.2f}, "
            f"confidence={confidence:.2f}), emotion={dominant_emotion.value}"
        )

        return sentiment.value, score

    def detect_emotions(self, text: str) -> Dict[str, float]:
        """
        Detect emotions in text.

        Args:
            text: Text to analyze

        Returns:
            Dictionary mapping emotions to scores
        """
        text_lower = text.lower()
        emotions = self.emotion_analyzer.detect_emotions(text_lower)
        return {e.value: emotions.get(e, 0.0) for e in Emotion}

    def batch_analyze(self, messages: List[str]) -> Dict[str, any]:
        """
        Analyze sentiment across multiple messages (alias for analyze_batch).

        Args:
            messages: List of message texts

        Returns:
            Dictionary with aggregated sentiment analysis
        """
        return self.analyze_batch(messages)

    def analyze_batch(self, messages: List[str]) -> List[Tuple[str, float]]:
        """
        Analyze sentiment across multiple messages.

        Args:
            messages: List of message texts

        Returns:
            List of (sentiment, score) tuples
        """
        if not messages:
            return []

        results = [self.analyze(msg) for msg in messages]
        return results

    def _detect_conflict_level(self, text_lower: str) -> float:
        """Calculate conflict level (0-1)."""
        score = 0.0

        # Check direct disagreement
        if self.conflict_detector.detect_direct_disagreement(text_lower):
            score += 0.3

        # Check blame
        if self.conflict_detector.detect_blame(text_lower):
            score += 0.3

        # Check for conflict keywords
        conflict_keyword_count = sum(
            1 for word in SentimentKeywords.CONFLICT_WORDS
            if word in text_lower
        )
        if conflict_keyword_count > 0:
            score += min(conflict_keyword_count * 0.1, 0.2)

        # Check ALL CAPS
        if self.pattern_detector.detect_all_caps(text_lower):
            score += 0.2

        return min(score, 1.0)

    def _analyze_sentiment(self, text_lower: str) -> Tuple[Sentiment, float, List[str]]:
        """
        Analyze sentiment direction and intensity.

        Returns:
            Tuple of (sentiment, score -1 to 1, keywords)
        """
        positive_score = 0.0
        negative_score = 0.0
        keywords = []

        # Count positive words
        for word in SentimentKeywords.POSITIVE_WORDS:
            count = len(re.findall(rf'\b{word}\b', text_lower))
            if count > 0:
                positive_score += count
                keywords.append(word)

        # Count negative words
        for word in SentimentKeywords.NEGATIVE_WORDS:
            count = len(re.findall(rf'\b{word}\b', text_lower))
            if count > 0:
                negative_score += count
                keywords.append(word)

        # Handle negation (not good = negative)
        if self.pattern_detector.detect_negation_reversal(text_lower):
            positive_score, negative_score = negative_score, positive_score

        # Calculate net score (-1 to 1)
        total = positive_score + negative_score
        if total == 0:
            score = 0.0
        else:
            score = (positive_score - negative_score) / (total + 1)

        # Detect patterns that intensify sentiment
        if self.pattern_detector.detect_all_caps(text_lower):
            score = score * 1.3  # Intensify

        repeated_punct, punct_type = self.pattern_detector.detect_repeated_punctuation(text_lower)
        if repeated_punct:
            if punct_type == "exclamation" and score > 0:
                score = score * 1.2  # Intensify positive
            elif punct_type == "question" and score < 0:
                score = score * 1.2  # Intensify negative

        # Clamp to [-1, 1]
        score = max(-1.0, min(1.0, score))

        # Determine sentiment
        if score > 0.2:
            sentiment = Sentiment.POSITIVE
        elif score < -0.2:
            sentiment = Sentiment.NEGATIVE
        else:
            sentiment = Sentiment.NEUTRAL

        return sentiment, score, keywords

    def _create_conflict_score(self, text_lower: str) -> SentimentScore:
        """Create a conflict sentiment score."""
        emotions = self.emotion_analyzer.detect_emotions(text_lower)
        dominant_emotion = self.emotion_analyzer.get_dominant_emotion(emotions)

        # Extract conflict keywords
        keywords = [
            word for word in SentimentKeywords.CONFLICT_WORDS
            if word in text_lower
        ]

        return SentimentScore(
            sentiment=Sentiment.CONFLICT,
            score=-0.7,  # Conflict is negative
            dominant_emotion=dominant_emotion,
            emotions={e.value: emotions.get(e, 0.0) for e in Emotion},
            keywords=keywords[:10],
            confidence=0.8,
        )

    def _calculate_confidence(
        self,
        text: str,
        keywords: List[str],
        emotions: Dict[Emotion, float],
    ) -> float:
        """
        Calculate confidence in sentiment analysis.

        Args:
            text: Original text
            keywords: Found sentiment keywords
            emotions: Emotion scores

        Returns:
            Confidence score (0-1)
        """
        confidence = 0.3  # Base confidence

        # More keywords = higher confidence
        confidence += min(len(keywords) * 0.1, 0.3)

        # Longer text = more confident
        text_len = len(text.split())
        confidence += min(text_len * 0.01, 0.2)

        # Strong emotions = higher confidence
        max_emotion = max(emotions.values()) if emotions else 0
        confidence += max_emotion * 0.2

        return min(confidence, 1.0)
