# GroupMind Bot - Development Guide

## Project Overview

GroupMind is an intelligent Telegram group chat analyzer that uses AI to:
- Monitor group conversations in real-time
- Generate automated summaries of discussions
- Analyze sentiment and emotional tone
- Provide conversation insights

## Architecture

### Core Components

```
bot/
├── main.py                 # BotManager - Telegram bot orchestration
├── handlers/
│   ├── commands.py        # Command handlers (/start, /help, /summary)
│   └── messages.py        # Message processing pipeline
├── models/
│   ├── database.py        # SQLAlchemy ORM models (Group, User, Message, Summary)
│   └── schemas.py         # Pydantic validation schemas
├── services/
│   ├── deepseek.py        # DeepSeek AI API integration
│   ├── sentiment.py       # Sentiment analysis (positive/negative/neutral)
│   └── summarizer.py      # Conversation summarization
└── utils/
    ├── rate_limiter.py    # Rate limiting
    └── queue.py           # Job queue management
```

### Infrastructure

- **Database**: PostgreSQL with async SQLAlchemy ORM
- **Cache**: Redis for rate limiting and job queue
- **Message Queue**: RQ (Redis Queue) for background jobs
- **API**: DeepSeek for AI summarization

### Docker Services

```yaml
postgres:   # Database server (port 5432)
redis:      # Cache and queue (port 6379)
bot:        # Telegram bot service
worker:     # Background job processor
```

## Getting Started

### Prerequisites
- Docker and Docker Compose
- Python 3.12+
- Telegram Bot Token (from BotFather)
- DeepSeek API Key

### Setup

```bash
# 1. Clone and setup
cd /workspaces/GroupMind
cp .env.example .env

# 2. Add your credentials to .env
TELEGRAM_BOT_TOKEN=your_token_here
DEEPSEEK_API_KEY=your_key_here

# 3. Start services
docker-compose up -d

# 4. Run tests
python -m pytest tests/ -v
```

### Running the Bot

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f bot

# Stop services
docker-compose down
```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_services.py -v

# Run with coverage
pytest tests/ --cov=bot --cov-report=html

# Run only passing tests
pytest tests/ -v -m "not skip"
```

### Test Coverage

- **Service Layer**: 17/17 tests (100%) - sentiment analysis, summarization, AI
- **Database Models**: 8/8 tests (100%) - ORM models and relationships
- **Integration**: 7/10 tests (70%) - end-to-end workflows
- **Total**: 32 active tests passing, 34 skipped (old architecture)

### Code Quality

```bash
# Check for style issues
pylint bot/

# Format code
black bot/

# Type checking
mypy bot/
```

## Key Features

### Message Handling
- Automatic message capture in group chats
- User and group tracking
- Timestamp management
- Rate limiting per user

### Summarization
- Retrieves last 50 messages (24-hour window)
- Sends to DeepSeek for AI processing
- Supports multiple languages
- Graceful fallback if API unavailable

### Sentiment Analysis
- Positive/negative/neutral classification
- Emotion detection (joy, anger, sadness, etc.)
- Batch analysis support
- Configurable thresholds

### Rate Limiting
- Per-user message limits
- Command rate limiting
- Sliding window algorithm
- Configurable per-minute and per-hour limits

## API Integration

### DeepSeek API

The bot uses DeepSeek's chat API for summarization:

```python
from bot.services.deepseek import DeepSeekClient, Message

client = DeepSeekClient(api_key=key)
await client.initialize()

messages = [
    Message(user="alice", text="Hello"),
    Message(user="bob", text="Hi there!"),
]

summary = await client.summarize_messages(messages)
await client.close()
```

### Telegram Bot API

Uses `python-telegram-bot` v22.5 with async support:

```python
from telegram import Update
from telegram.ext import ContextTypes

async def command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello!")
```

## Database Schema

### Tables

- **groups**: Telegram groups being monitored
- **users**: Group members with privacy settings
- **messages**: Individual messages with sentiment
- **summaries**: AI-generated conversation summaries
- **audit_logs**: Activity tracking

### Key Models

```python
Group(group_id, title, member_count, is_active, bot_added_at)
User(user_id, username, first_name, opt_out_status)
Message(message_id, group_id, user_id, text, sentiment, timestamp)
Summary(summary_id, group_id, summary_text, period_start, period_end)
```

## Configuration

### Environment Variables

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token

# DeepSeek AI
DEEPSEEK_API_KEY=your_api_key

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname

# Redis
REDIS_URL=redis://localhost:6379/0

# Logging
LOG_LEVEL=INFO
```

### Rate Limits

Default settings in `BotManager`:
- **Per-minute**: 10 messages
- **Per-hour**: 100 messages

Configurable via constructor:
```python
bot = BotManager(
    token=token,
    database_url=db_url,
    max_messages_per_minute=10,
    max_messages_per_hour=100,
)
```

## Deployment

### Local Development

```bash
docker-compose up -d
python -m pytest tests/ -v
```

### Production Deployment

1. Use container orchestration (Kubernetes, ECS)
2. Configure production database
3. Use SSL for Telegram webhook (optional)
4. Set up monitoring and logging
5. Configure backups for PostgreSQL

## Troubleshooting

### Bot Not Responding

1. Check logs: `docker-compose logs bot`
2. Verify credentials in .env
3. Check database connection: `docker-compose logs postgres`
4. Verify Redis connection: `docker-compose logs redis`

### Messages Not Being Stored

1. Check database: `docker-compose exec postgres psql`
2. Verify group is registered: `SELECT * FROM groups;`
3. Check message table: `SELECT * FROM messages;`

### AI Summarization Failed

1. Verify DeepSeek API key
2. Check token limits: `docker-compose logs bot | grep "token"`
3. Verify API rate limits

## Performance Optimization

### Current Optimizations

- Async/await throughout for concurrency
- Connection pooling (SQLAlchemy)
- Redis caching for rate limiting
- Async message processing
- Batch sentiment analysis

### Future Improvements

- Add caching layer for summaries
- Implement message deduplication
- Optimize database queries with indexes
- Add background worker pool scaling
- Implement message compression

## Security

### Current Measures

- Rate limiting on commands
- User opt-out functionality
- Soft delete for data retention
- Async operations for thread safety

### Recommendations

- Enable TLS for Redis
- Use PostgreSQL authentication
- Implement user permissions
- Add message encryption
- Regular security audits

## Contributing

1. Create feature branch
2. Add tests for new functionality
3. Ensure all tests pass: `pytest tests/ -v`
4. Follow PEP 8 style guide
5. Submit pull request

## License

MIT

## Support

For issues or questions, open a GitHub issue or contact the maintainer.
