"""
Message summarization service for GroupMind.

This module provides:
- Master prompt template for high-quality group chat summaries
- Extraction of key decisions, action items, main topics, engagement
- Context optimization with smart truncation
- Language detection and appropriate response language
- Statistical analysis of conversations
"""

import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from collections import Counter
from enum import Enum

from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class Language(str, Enum):
    """Supported languages for summaries."""
    ENGLISH = "en"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    PORTUGUESE = "pt"
    RUSSIAN = "ru"
    CHINESE = "zh"
    JAPANESE = "ja"


class ConversationStatistics(BaseModel):
    """Statistics about a conversation."""
    message_count: int = Field(..., ge=0)
    participant_count: int = Field(..., ge=0)
    unique_participants: List[str] = Field(default_factory=list)
    time_range: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    avg_message_length: float = Field(default=0, ge=0)
    most_active_users: List[Tuple[str, int]] = Field(default_factory=list)

    class Config:
        """Pydantic config."""
        arbitrary_types_allowed = True


class SummaryExtraction(BaseModel):
    """Extracted summary components."""
    main_topics: List[str] = Field(default_factory=list, min_items=0, max_items=10)
    key_decisions: List[str] = Field(default_factory=list, min_items=0, max_items=10)
    action_items: List[str] = Field(default_factory=list, min_items=0, max_items=10)
    participant_engagement: Dict[str, str] = Field(default_factory=dict)
    overall_sentiment: str = Field(default="neutral")
    summary_text: str = Field(..., min_length=1, max_length=2000)

    @validator("overall_sentiment")
    def validate_sentiment(cls, v):
        """Validate sentiment is one of predefined values."""
        valid_sentiments = ["positive", "negative", "neutral", "mixed"]
        if v.lower() not in valid_sentiments:
            return "neutral"
        return v.lower()


class LanguageDetector:
    """Detects language of text."""

    # Common words in different languages for detection
    LANGUAGE_PATTERNS = {
        Language.ENGLISH: [
            "the", "be", "to", "of", "and", "a", "in", "that", "have",
            "it", "is", "for", "on", "with", "he", "as", "you", "do",
        ],
        Language.SPANISH: [
            "el", "la", "de", "que", "y", "a", "en", "un", "ser", "se",
            "no", "haber", "por", "con", "su", "para", "es", "al", "lo",
        ],
        Language.FRENCH: [
            "le", "de", "un", "et", "à", "être", "en", "que", "il", "avoir",
            "ne", "je", "son", "que", "se", "pas", "plus", "pouvoir", "par",
        ],
        Language.GERMAN: [
            "der", "die", "und", "in", "den", "von", "zu", "das", "mit",
            "sich", "des", "auf", "für", "ist", "im", "dem", "nicht",
        ],
        Language.PORTUGUESE: [
            "de", "a", "o", "que", "e", "do", "da", "em", "um", "para",
            "é", "com", "não", "uma", "os", "no", "se", "na", "por",
        ],
        Language.RUSSIAN: [
            "и", "в", "во", "не", "что", "он", "на", "я", "с", "со",
            "а", "то", "все", "она", "так", "его", "но", "да", "ты",
        ],
        Language.CHINESE: [
            "的", "一", "是", "在", "不", "了", "有", "人", "这", "中",
            "大", "为", "上", "个", "国", "我", "以", "要", "他",
        ],
        Language.JAPANESE: [
            "の", "に", "は", "を", "た", "が", "で", "て", "と", "し",
            "れ", "さ", "ある", "いる", "も", "する", "から", "な", "こと",
        ],
    }

    @classmethod
    @classmethod
    def detect_language(cls, text: str) -> Language:
        """
        Detect language of text.

        Args:
            text: Text to analyze

        Returns:
            Detected language
        """
        if not text or len(text.strip()) == 0:
            return Language.ENGLISH

        # Convert to lowercase and split
        words = text.lower().split()
        words_set = set(words)

        # Count pattern matches
        scores = {}
        for lang, patterns in cls.LANGUAGE_PATTERNS.items():
            pattern_set = set(patterns)
            score = len(words_set & pattern_set)
            scores[lang] = score

        # Return language with highest score
        if max(scores.values()) == 0:
            return Language.ENGLISH

        detected = max(scores.items(), key=lambda x: x[1])[0]
        logger.debug(f"Detected language: {detected}")
        return detected

    def detect(self, text: str) -> str:
        """
        Detect language of text (instance method wrapper).

        Args:
            text: Text to analyze

        Returns:
            Detected language code
        """
        return self.detect_language(text).value


class ContextOptimizer:
    """Optimizes context for summarization."""

    # Token to character ratio (approximation)
    CHARS_PER_TOKEN = 4
    MAX_CONTEXT_TOKENS = 100000  # Keep 100K tokens for context (leave room for response)
    MAX_CONTEXT_CHARS = MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN

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
    def optimize_context(
        cls,
        formatted_messages: str,
        statistics: ConversationStatistics,
    ) -> Tuple[str, bool]:
        """
        Optimize context to fit within token limits.

        Args:
            formatted_messages: Formatted message text
            statistics: Conversation statistics

        Returns:
            Tuple of (optimized_text, was_truncated)
        """
        if len(formatted_messages) <= cls.MAX_CONTEXT_CHARS:
            return formatted_messages, False

        logger.warning(
            f"Context exceeds limit: {cls.count_tokens(formatted_messages)}/{cls.MAX_CONTEXT_TOKENS} tokens"
        )

        # Strategy 1: Keep recent messages (last 70% of token budget)
        recent_budget = int(cls.MAX_CONTEXT_CHARS * 0.7)
        recent_messages = formatted_messages[-recent_budget:]

        # Strategy 2: Sample from beginning and end
        beginning_budget = int(cls.MAX_CONTEXT_CHARS * 0.3)
        beginning_messages = formatted_messages[:beginning_budget]
        separator = "\n\n... [messages omitted for length] ...\n\n"

        optimized = beginning_messages + separator + recent_messages
        optimized = optimized[-cls.MAX_CONTEXT_CHARS:]  # Final trim

        logger.info(
            f"Context optimized from {cls.count_tokens(formatted_messages)} "
            f"to {cls.count_tokens(optimized)} tokens"
        )

        return optimized, True


class ParticipantAnalyzer:
    """Analyzes participant engagement patterns."""

    @staticmethod
    def analyze_engagement(
        messages: List[Dict[str, Any]],
    ) -> Dict[str, str]:
        """
        Analyze participant engagement levels.

        Args:
            messages: List of message dictionaries

        Returns:
            Dictionary mapping user to engagement level
        """
        if not messages:
            return {}

        # Count messages per user
        user_message_counts = Counter()
        user_first_seen = {}
        user_last_seen = {}

        for msg in messages:
            user = msg.get("user", "Unknown")
            if user not in user_message_counts:
                user_message_counts[user] = 0
                user_first_seen[user] = msg.get("timestamp")

            user_message_counts[user] += 1
            user_last_seen[user] = msg.get("timestamp")

        total_messages = sum(user_message_counts.values())
        if total_messages == 0:
            return {}

        engagement = {}
        for user, count in user_message_counts.items():
            percentage = (count / total_messages) * 100

            # Determine engagement level
            if percentage > 30:
                level = "Very Active"
            elif percentage > 15:
                level = "Active"
            elif percentage > 5:
                level = "Moderate"
            else:
                level = "Quiet"

            engagement[user] = f"{level} ({count} messages)"

        return engagement


class ConversationAnalyzer:
    """Analyzes conversation for structure and content."""

    def analyze(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze a conversation.

        Args:
            messages: List of message dicts with 'text' and 'user' keys

        Returns:
            Dictionary with analysis results
        """
        if not messages:
            return {
                "action_items": [],
                "decisions": [],
                "topics": [],
                "message_count": 0,
                "participant_count": 0,
            }

        # Combine all texts
        combined_text = " ".join([msg.get("text", "") for msg in messages])
        
        # Get unique participants
        participants = set(msg.get("user", "Unknown") for msg in messages if msg.get("user"))

        return {
            "action_items": self.extract_action_items(combined_text),
            "decisions": self.extract_decisions(combined_text),
            "topics": self.extract_topics(combined_text),
            "message_count": len(messages),
            "participant_count": len(participants),
            "participants": list(participants),
        }

    @staticmethod
    def extract_action_items(text: str) -> List[str]:
        """
        Extract potential action items from text.

        Args:
            text: Conversation text

        Returns:
            List of potential action items
        """
        action_patterns = [
            r"(?:todo|to do|task|action|need to|should|must|have to|will)[\s:]+([^.\n]+)",
            r"(?:by|until|deadline)[\s:]+([^.\n]+)",
            r"(?:assign|assign to|give to)[\s:]+([^.\n]+)",
        ]

        items = set()
        for pattern in action_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            items.update(matches)

        return list(items)[:10]

    @staticmethod
    def extract_decisions(text: str) -> List[str]:
        """
        Extract decisions from text.

        Args:
            text: Conversation text

        Returns:
            List of decisions
        """
        decision_patterns = [
            r"(?:decided|decision|agreed|agree to|will|plan to)[\s:]+([^.\n]+[.!]?)",
            r"(?:we|we're|we've)[\s]+([^.]+[.!]?)",
            r"(?:approved|approved)[\s:]+([^.\n]+)",
        ]

        decisions = set()
        for pattern in decision_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            decisions.update(matches)

        return list(decisions)[:10]

    @staticmethod
    def extract_topics(text: str, limit: int = 5) -> List[str]:
        """
        Extract main topics from text.

        Args:
            text: Conversation text
            limit: Maximum topics to extract

        Returns:
            List of main topics
        """
        # Split into sentences
        sentences = re.split(r'[.!?]+', text)

        # Extract noun phrases (simplified)
        topics = set()
        for sentence in sentences:
            # Look for capitalized phrases (often topics)
            caps_phrases = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', sentence)
            topics.update(caps_phrases)

        return list(topics)[:limit]


class SummarizerPromptBuilder:
    """Builds prompts for summarization."""

    LANGUAGE_PROMPTS = {
        Language.ENGLISH: {
            "system": (
                "You are an expert at analyzing and summarizing Telegram group conversations. "
                "Provide clear, structured summaries that capture the essence of discussions. "
                "Be concise but comprehensive."
            ),
            "summary_instruction": (
                "Create a concise summary of this Telegram group chat covering the following aspects in your response:\n"
                "1. 3-5 main topics discussed\n"
                "2. Key decisions made\n"
                "3. Action items that need attention\n"
                "4. Overall sentiment of the conversation\n"
                "5. Notable insights or observations\n\n"
                "Format your response as a structured summary with clear sections."
            ),
        },
        Language.SPANISH: {
            "system": (
                "Eres un experto en analizar y resumir conversaciones de grupos de Telegram. "
                "Proporciona resúmenes claros y estructurados que capturen la esencia de las discusiones."
            ),
            "summary_instruction": (
                "Crea un resumen conciso de este chat grupal de Telegram cubriendo:\n"
                "1. 3-5 temas principales\n"
                "2. Decisiones clave\n"
                "3. Elementos de acción\n"
                "4. Sentimiento general\n"
                "5. Observaciones notables"
            ),
        },
        Language.FRENCH: {
            "system": (
                "Vous êtes un expert en analyse et résumé de conversations de groupe Telegram. "
                "Fournissez des résumés clairs et structurés."
            ),
            "summary_instruction": (
                "Créez un résumé concis de cette conversation de groupe Telegram couvrant:\n"
                "1. 3-5 sujets principaux\n"
                "2. Décisions clés\n"
                "3. Éléments d'action\n"
                "4. Sentiment général\n"
                "5. Observations remarquables"
            ),
        },
        Language.GERMAN: {
            "system": (
                "Sie sind ein Experte für die Analyse und Zusammenfassung von Telegram-Gruppengesprächen. "
                "Geben Sie klare, strukturierte Zusammenfassungen."
            ),
            "summary_instruction": (
                "Erstellen Sie eine prägnante Zusammenfassung dieses Telegram-Gruppengesprächs mit:\n"
                "1. 3-5 Hauptthemen\n"
                "2. Wichtige Entscheidungen\n"
                "3. Aktionspunkte\n"
                "4. Allgemeine Stimmung\n"
                "5. Bemerkenswerte Beobachtungen"
            ),
        },
        Language.PORTUGUESE: {
            "system": (
                "Você é um especialista em análise e resumo de conversas de grupos do Telegram. "
                "Forneça resumos claros e estruturados."
            ),
            "summary_instruction": (
                "Crie um resumo conciso desta conversa de grupo do Telegram abordando:\n"
                "1. 3-5 temas principais\n"
                "2. Decisões chave\n"
                "3. Itens de ação\n"
                "4. Sentimento geral\n"
                "5. Observações notáveis"
            ),
        },
        Language.RUSSIAN: {
            "system": (
                "Вы являетесь экспертом в анализе и резюмировании групповых разговоров в Telegram. "
                "Предоставляйте четкие, структурированные резюме."
            ),
            "summary_instruction": (
                "Создайте краткое резюме этого группового чата Telegram, охватывающее:\n"
                "1. 3-5 основных тем\n"
                "2. Ключевые решения\n"
                "3. Пункты действий\n"
                "4. Общее настроение\n"
                "5. Примечательные наблюдения"
            ),
        },
        Language.CHINESE: {
            "system": (
                "您是Telegram群组对话分析和总结的专家。"
                "提供清晰、结构化的总结。"
            ),
            "summary_instruction": (
                "创建这个Telegram群组聊天的简明总结，涵盖：\n"
                "1. 3-5个主要主题\n"
                "2. 关键决策\n"
                "3. 行动项目\n"
                "4. 总体情绪\n"
                "5. 显著观察"
            ),
        },
        Language.JAPANESE: {
            "system": (
                "Telegramグループ会話の分析と要約の専門家です。"
                "明確で構造化された要約を提供します。"
            ),
            "summary_instruction": (
                "このTelegramグループチャットの簡潔な要約を作成し、以下をカバーしてください：\n"
                "1. 3-5の主要なトピック\n"
                "2. 重要な決定\n"
                "3. アクション項目\n"
                "4. 全体的なセンチメント\n"
                "5. 注目すべき観察"
            ),
        },
    }

    @classmethod
    def build_summary_prompt(
        cls,
        messages_context: str,
        statistics: ConversationStatistics,
        language: Language = Language.ENGLISH,
    ) -> str:
        """
        Build comprehensive summarization prompt.

        Args:
            messages_context: Formatted message context
            statistics: Conversation statistics
            language: Target language for summary

        Returns:
            Complete prompt for summarization
        """
        prompts = cls.LANGUAGE_PROMPTS.get(language, cls.LANGUAGE_PROMPTS[Language.ENGLISH])

        stats_section = cls._format_statistics(statistics, language)

        prompt = f"""Analyze and summarize the following Telegram group conversation:

{stats_section}

CONVERSATION:
{messages_context}

{prompts['summary_instruction']}

Remember to:
- Be specific and cite examples when relevant
- Focus on actionable insights
- Identify who is responsible for action items
- Maintain objectivity and clarity
"""

        return prompt

    @classmethod
    def _format_statistics(
        cls,
        statistics: ConversationStatistics,
        language: Language = Language.ENGLISH,
    ) -> str:
        """
        Format statistics for inclusion in prompt.

        Args:
            statistics: Conversation statistics
            language: Language for formatting

        Returns:
            Formatted statistics string
        """
        labels = {
            Language.ENGLISH: {
                "messages": "Total Messages",
                "participants": "Participants",
                "timerange": "Time Range",
                "avglen": "Average Message Length",
                "mostactive": "Most Active Users",
            },
            Language.SPANISH: {
                "messages": "Mensajes Totales",
                "participants": "Participantes",
                "timerange": "Rango de Tiempo",
                "avglen": "Longitud Promedio de Mensaje",
                "mostactive": "Usuarios Más Activos",
            },
            Language.FRENCH: {
                "messages": "Messages Totaux",
                "participants": "Participants",
                "timerange": "Plage Temporelle",
                "avglen": "Longueur Moyenne des Messages",
                "mostactive": "Utilisateurs les Plus Actifs",
            },
            Language.GERMAN: {
                "messages": "Gesamtnachrichten",
                "participants": "Teilnehmer",
                "timerange": "Zeitbereich",
                "avglen": "Durchschnittliche Nachrichtenlänge",
                "mostactive": "Aktivste Benutzer",
            },
        }

        lang_labels = labels.get(language, labels[Language.ENGLISH])

        most_active_str = ", ".join([
            f"{name} ({count})" for name, count in statistics.most_active_users[:3]
        ]) if statistics.most_active_users else "N/A"

        stats_text = f"""CONVERSATION STATISTICS:
- {lang_labels['messages']}: {statistics.message_count}
- {lang_labels['participants']}: {statistics.participant_count}
- {lang_labels['timerange']}: {statistics.time_range or 'N/A'}
- {lang_labels['avglen']}: {statistics.avg_message_length:.1f} characters
- {lang_labels['mostactive']}: {most_active_str}
"""

        return stats_text


class Summarizer:
    """Main summarizer orchestrator."""

    def __init__(self):
        """Initialize summarizer."""
        self.language_detector = LanguageDetector()
        self.context_optimizer = ContextOptimizer()
        self.participant_analyzer = ParticipantAnalyzer()
        self.conversation_analyzer = ConversationAnalyzer()
        self.prompt_builder = SummarizerPromptBuilder()

    def analyze_conversation(
        self,
        messages: List[Dict[str, Any]],
    ) -> Tuple[ConversationStatistics, str, bool]:
        """
        Analyze conversation and prepare context.

        Args:
            messages: List of message dictionaries

        Returns:
            Tuple of (statistics, formatted_messages, was_truncated)
        """
        if not messages:
            raise ValueError("Empty message list")

        # Calculate statistics
        statistics = self._calculate_statistics(messages)

        # Format messages
        formatted_messages = self._format_messages(messages)

        # Optimize context
        optimized_messages, was_truncated = self.context_optimizer.optimize_context(
            formatted_messages,
            statistics,
        )

        logger.info(
            f"Conversation analyzed: {statistics.message_count} messages, "
            f"{statistics.participant_count} participants, "
            f"truncated={was_truncated}"
        )

        return statistics, optimized_messages, was_truncated

    def build_prompt(
        self,
        statistics: ConversationStatistics,
        formatted_messages: str,
        detected_language: Optional[Language] = None,
    ) -> Tuple[str, Language]:
        """
        Build summarization prompt.

        Args:
            statistics: Conversation statistics
            formatted_messages: Formatted message context
            detected_language: Detected language (auto-detected if None)

        Returns:
            Tuple of (prompt, language)
        """
        if not detected_language:
            # Detect from messages
            sample_text = formatted_messages[:1000]
            detected_language = self.language_detector.detect_language(sample_text)

        prompt = self.prompt_builder.build_summary_prompt(
            formatted_messages,
            statistics,
            detected_language,
        )

        logger.info(f"Prompt built for language: {detected_language}")
        return prompt, detected_language

    def get_summary_prompt(
        self,
        conversation: str,
        language: str = "en",
        style: str = "concise",
    ) -> str:
        """
        Get a summary prompt for conversation.

        Args:
            conversation: The conversation text
            language: Language code (e.g., 'en', 'es')
            style: Summary style ('concise', 'detailed', 'bullet_points')

        Returns:
            Generated prompt string
        """
        # Create a simple statistics object
        statistics = ConversationStatistics(
            message_count=len(conversation.split()),
            participant_count=1,
        )

        # Map language code to Language enum
        lang_map = {lang.value: lang for lang in Language}
        detected_lang = lang_map.get(language, Language.ENGLISH)

        prompt = self.prompt_builder.build_summary_prompt(
            conversation,
            statistics,
            detected_lang,
        )

        return prompt

    def _calculate_statistics(
        self,
        messages: List[Dict[str, Any]],
    ) -> ConversationStatistics:
        """Calculate conversation statistics."""
        if not messages:
            return ConversationStatistics(
                message_count=0,
                participant_count=0,
            )

        # Extract users
        users = set()
        total_length = 0
        timestamps = []

        for msg in messages:
            user = msg.get("user")
            if user:
                users.add(user)

            text = msg.get("text", "")
            total_length += len(text)

            timestamp = msg.get("timestamp")
            if timestamp:
                timestamps.append(timestamp)

        # Calculate engagement
        engagement = self.participant_analyzer.analyze_engagement(messages)
        most_active = sorted(
            engagement.items(),
            key=lambda x: int(re.search(r'(\d+)', x[1]).group(1)) if re.search(r'(\d+)', x[1]) else 0,
            reverse=True,
        )[:3]

        # Time range
        time_range = None
        if timestamps:
            try:
                start = min(timestamps)
                end = max(timestamps)
                time_range = f"{start} to {end}" if isinstance(start, str) else "N/A"
            except Exception:
                pass

        return ConversationStatistics(
            message_count=len(messages),
            participant_count=len(users),
            unique_participants=list(users),
            time_range=time_range,
            avg_message_length=total_length / len(messages) if messages else 0,
            most_active_users=[(name, int(re.search(r'(\d+)', count).group(1)))
                              for name, count in most_active],
        )

    def _format_messages(self, messages: List[Dict[str, Any]]) -> str:
        """Format messages into readable text."""
        lines = []
        for msg in messages:
            timestamp = msg.get("timestamp", "unknown")
            user = msg.get("user", "Unknown")
            text = msg.get("text", "")

            # Truncate very long messages
            if len(text) > 500:
                text = text[:500] + "..."

            lines.append(f"[{timestamp}] {user}: {text}")

        return "\n".join(lines)
