# GroupMind - AI-Powered Telegram Group Summarizer

A sophisticated Telegram bot that automatically summarizes group conversations using DeepSeek AI, with sentiment analysis, rate limiting, and Redis-based job queuing.

## Features

### Core Capabilities
- 🤖 **AI-Powered Summarization**: Uses DeepSeek API (128K token context) to generate intelligent summaries
- 💬 **Conversation Analysis**: Extracts key topics, decisions, and action items
- 😊 **Sentiment Analysis**: Keyword-based emotion detection and conflict pattern recognition
- 🌍 **Multilingual Support**: Handles 8+ languages automatically
- ⚡ **Rate Limiting**: Three-tier system (FREE/PRO/ENTERPRISE) with token bucket algorithm
- 📊 **Message Batching**: Efficient batch processing with Redis queue
- 🔐 **Privacy Controls**: Automatic sensitive data filtering
- 📈 **Statistics Tracking**: Captures detailed usage and performance metrics

### Technical Highlights
- **Async/Await**: Full async implementation for high concurrency
- **SQLAlchemy ORM**: Type-safe database operations with soft deletion
- **Redis Integration**: Distributed rate limiting and job queue
- **Telegram Bot API**: Latest python-telegram-bot v20+
- **Comprehensive Testing**: >80% code coverage with pytest

## Project Structure

```
GroupMind/
├── bot/
│   ├── main.py                    # Core bot entry point
│   ├── handlers/
│   │   ├── commands.py            # /start, /summary, /help handlers
│   │   └── messages.py            # Message capture and batching
│   ├── models/
│   │   ├── database.py            # SQLAlchemy ORM models
│   │   └── schemas.py             # Pydantic validation schemas
│   ├── services/
│   │   ├── deepseek.py            # DeepSeek API client
│   │   ├── sentiment.py           # Sentiment analysis engine
│   │   └── summarizer.py          # Summary generation
│   └── utils/
│       ├── queue.py               # Redis job queue
│       └── rate_limiter.py        # Token bucket rate limiting
├── worker/
│   └── processor.py               # Background summary processor
├── migrations/                    # Alembic database migrations
│   ├── env.py                     # Migration configuration
│   ├── script.py.mako             # Migration template
│   └── versions/
│       └── 001_initial.py         # Initial schema migration
├── tests/                         # Comprehensive test suite
│   ├── conftest.py                # Pytest fixtures
│   ├── test_handlers.py           # Handler tests
│   ├── test_services.py           # Service tests
│   ├── test_models.py             # Model and utility tests
│   └── test_integration.py        # End-to-end workflows
├── requirements.txt               # Python dependencies
├── alembic.ini                    # Alembic configuration
├── docker-compose.yml             # Docker services
├── TESTS.md                       # Testing documentation
└── README.md                      # This file
```

## Installation

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- Docker & Docker Compose (optional)

### Setup

1. **Clone the repository**
```bash
git clone <repository-url>
cd GroupMind
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env with your credentials:
# - TELEGRAM_BOT_TOKEN
# - DEEPSEEK_API_KEY
# - DATABASE_URL
# - REDIS_URL
```

5. **Initialize database**
```bash
# Install Alembic (if not already in requirements)
pip install alembic

# Run migrations
alembic upgrade head
```

## Configuration

### Environment Variables

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_ADMIN_IDS=123456789,987654321

# AI Model
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_MODEL=deepseek-chat

# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost/groupmind
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40

# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Rate Limiting
RATE_LIMIT_REDIS_NAMESPACE=groupmind

# Feature Flags
ENABLE_SENTIMENT_ANALYSIS=true
ENABLE_CONFLICT_DETECTION=true
ENABLE_PRIVACY_FILTERING=true
```

## Running the Bot

### Using Python

```bash
# Start the main bot
python bot/main.py

# In another terminal, start the background worker
python worker/processor.py
```

### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Usage

### Commands

**`/start`** - Join the bot
```
Welcome to GroupMind! I'll help analyze your group conversations.
```

**`/summary`** - Request a summary of recent messages
```
Generates a comprehensive summary of the last 24 hours of conversation.
Rate limited based on subscription tier.
```

**`/help`** - Show available commands
```
Lists all commands and usage information.
```

### Rate Limiting

**FREE Tier**: 5 summaries/hour per user, 10 per group/day
**PRO Tier**: 30 summaries/hour per user, 100 per group/day
**ENTERPRISE Tier**: 200 summaries/hour per user, 1000 per group/day

## Database Schema

### Tables

**groups**
- Tracks Telegram groups
- Stores member count and activity status
- Soft deletion support

**users**
- Individual Telegram users
- Tracks opt-out preferences
- Maintains privacy settings

**messages**
- Captures group messages
- Stores sentiment analysis results
- Indexed for fast queries

**summaries**
- Stores generated summaries
- Tracks performance metrics
- Maintains multiple versions

**audit_logs**
- Logs all significant actions
- Supports compliance tracking
- Enables debugging

## API Integration

### DeepSeek API

The bot uses DeepSeek's chat completion endpoint with:
- 128K token context window
- Exponential backoff retry logic (3 attempts)
- Fallback simple summarizer
- Token usage tracking

```python
from bot.services.deepseek import DeepSeekClient

client = DeepSeekClient(api_key="your_key")
summary = await client.generate_summary(
    conversation="...",
    target_language="en",
    style="concise"
)
```

### Database Operations

Using SQLAlchemy async ORM:

```python
from bot.models.database import Group, Message
from sqlalchemy import select

# Query
async with async_session() as session:
    result = await session.execute(
        select(Message).where(Message.group_id == group_id)
    )
    messages = result.scalars().all()

# Create
message = Message(
    group_id=group_id,
    user_id=user_id,
    text="Hello!",
    timestamp=datetime.utcnow()
)
session.add(message)
await session.commit()
```

## Testing

### Run Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=bot --cov-report=html

# Specific test file
pytest tests/test_handlers.py

# Specific test
pytest tests/test_handlers.py::TestCommandHandler::test_start_command_new_user
```

### Test Structure

- **test_handlers.py**: Command and message handler tests
- **test_services.py**: Service layer tests (DeepSeek, sentiment, summarizer)
- **test_models.py**: Database model and utility tests
- **test_integration.py**: End-to-end workflow tests

### Coverage Goals

- Handlers: >90%
- Services: >85%
- Models: >90%
- Utils: >80%
- Overall: >80%

See [TESTS.md](TESTS.md) for comprehensive testing documentation.

## Development

### Code Style

```bash
# Format code
black bot tests

# Check imports
isort bot tests

# Lint
flake8 bot tests

# Type checking
mypy bot
```

### Running Development Tasks

```bash
# Using tox
tox -e dev      # Run tests in dev environment
tox -e lint     # Run linters
tox -e format   # Format code
tox -e coverage # Generate coverage report
```

## Database Migrations

The project uses Alembic for database schema management.

### Running Migrations

```bash
# Upgrade to latest version
alembic upgrade head

# Upgrade to specific revision
alembic upgrade abc123

# Downgrade one revision
alembic downgrade -1

# Create new migration
alembic revision --autogenerate -m "description"
```

### Migration Files

- `migrations/env.py` - Alembic configuration for async support
- `migrations/script.py.mako` - Migration template
- `migrations/versions/001_initial.py` - Initial schema with all tables

See [migrations/](migrations/) for details.

## Deployment

### Production Checklist

- [ ] Set strong DEEPSEEK_API_KEY
- [ ] Configure secure DATABASE_URL (with SSL)
- [ ] Set TELEGRAM_BOT_TOKEN securely
- [ ] Enable ENABLE_PRIVACY_FILTERING
- [ ] Configure proper LOG_LEVEL=INFO
- [ ] Set up database backups
- [ ] Configure Redis persistence
- [ ] Set up monitoring and alerting
- [ ] Run migrations on production database
- [ ] Set resource limits for worker processes
- [ ] Configure rate limiting appropriately

### Scaling Considerations

- **Horizontal Scaling**: Use Redis for distributed rate limiting
- **Database**: Connection pooling with SQLAlchemy
- **Worker Scaling**: Run multiple worker processes
- **Caching**: Redis for summary results
- **Load Balancing**: Use load balancer for multiple bot instances

## Monitoring

### Key Metrics

- Summary generation success rate
- Average processing time
- Rate limit hits per tier
- Redis connection health
- Database query performance
- Error rates and types

### Logging

Structured JSON logging for all operations:

```json
{
  "timestamp": "2025-01-17T10:30:00Z",
  "level": "INFO",
  "component": "DeepSeekClient",
  "message": "Summary generated",
  "group_id": "-9876543210",
  "tokens_used": 450,
  "processing_time_ms": 2500
}
```

## Troubleshooting

### Common Issues

**Bot not responding to commands**
- Check TELEGRAM_BOT_TOKEN is correct
- Verify bot is added to group with proper permissions
- Check logs for connection errors

**Summaries not generating**
- Verify DEEPSEEK_API_KEY is valid
- Check Redis connection
- Review DeepSeek API rate limits
- Check database connection

**Rate limiting too strict**
- Adjust tier settings in configuration
- Check Redis for stale keys
- Verify rate limiter logic

**Database connection issues**
- Verify DATABASE_URL format
- Check PostgreSQL is running
- Ensure database exists and user has permissions
- Check connection pool settings

## Architecture

### Data Flow

```
User Message
    ↓
Message Handler (privacy filtering)
    ↓
Sentiment Analyzer
    ↓
Redis Queue (batch storage)
    ↓
Background Worker
    ↓
DeepSeek API (with retry logic)
    ↓
Database Storage
    ↓
Telegram Notification
```

### Rate Limiting

Token bucket algorithm for distributed rate limiting:

```
User Request
    ↓
Check Redis bucket
    ↓
Tokens available? → YES → Process request
    ↓
        NO → Return rate limit error
```

## Security

- **Sensitive Data**: Automatically filtered from messages
- **Opt-out**: Users can completely opt out
- **Soft Deletion**: All data can be recovered
- **API Keys**: Environment variable based, not in code
- **Database**: Async connection pooling
- **Rate Limiting**: Prevents abuse

## Contributing

1. Create a feature branch
2. Write tests for new functionality
3. Ensure tests pass and coverage >80%
4. Submit pull request with description

## License

[Your License Here]

## Support

For issues or questions:
- Open an issue on GitHub
- Check existing documentation
- Review test cases for usage examples

## Changelog

### Version 1.0.0
- Initial release
- Core bot functionality
- DeepSeek integration
- Rate limiting system
- Comprehensive test suite
- Database migrations

# GroupMind