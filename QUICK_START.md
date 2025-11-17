# GroupMind - Quick Start Guide

## ⚡ 5-Minute Setup

### 1. Clone & Install
```bash
git clone <repo>
cd GroupMind
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Database
```bash
pip install alembic
alembic upgrade head
```

### 4. Run
```bash
# Terminal 1: Bot
python bot/main.py

# Terminal 2: Worker
python worker/processor.py
```

## 🧪 Testing

```bash
# Install test tools
pip install pytest pytest-asyncio pytest-cov aiosqlite

# Run all tests
pytest

# With coverage
pytest --cov=bot --cov-report=html
open htmlcov/index.html
```

## 📚 Documentation

| Topic | File |
|-------|------|
| **Setup Instructions** | [SETUP.md](SETUP.md) |
| **Architecture & Features** | [README.md](README.md) |
| **Testing Guide** | [TESTS.md](TESTS.md) |
| **Project Status** | [COMPLETION_SUMMARY.md](COMPLETION_SUMMARY.md) |

## 🔧 Common Commands

```bash
# Start bot
python bot/main.py

# Start worker
python worker/processor.py

# Run tests
pytest

# Run tests with coverage
pytest --cov=bot

# Format code
black bot tests

# Lint code
flake8 bot tests

# Type check
mypy bot

# Database migrations
alembic current          # Show current version
alembic upgrade head     # Apply all migrations
alembic downgrade -1     # Undo last migration
```

## 🐳 Docker

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## 📁 Project Structure

```
bot/              - Main bot application
├── handlers/     - Command & message handlers
├── models/       - Database models & schemas
├── services/     - DeepSeek, sentiment, summarizer
├── utils/        - Queue & rate limiter
└── main.py       - Entry point

worker/           - Background job processor
migrations/       - Database migrations
tests/            - Comprehensive test suite
```

## 🚀 Key Features

- **AI Summarization** - DeepSeek API integration
- **Rate Limiting** - Token bucket algorithm
- **Sentiment Analysis** - Emotion & conflict detection
- **Async/Await** - Full async implementation
- **Database** - SQLAlchemy ORM with soft deletion
- **Redis Queue** - Distributed job processing
- **Comprehensive Tests** - 150+ test cases

## ✅ Checklist for Production

- [ ] Configure all environment variables
- [ ] Run database migrations
- [ ] Run all tests: `pytest`
- [ ] Review coverage: `pytest --cov=bot`
- [ ] Enable monitoring
- [ ] Set up backups
- [ ] Configure logging
- [ ] Deploy with Docker Compose

## 🆘 Troubleshooting

**Tests fail?**
```bash
# Install missing dependency
pip install aiosqlite pytest-asyncio

# Run with verbose output
pytest -v --tb=short
```

**Database connection error?**
```bash
# Check PostgreSQL
psql --version
psql -U postgres -d postgres

# Verify DATABASE_URL in .env
# Format: postgresql+asyncpg://user:password@host:port/database
```

**Redis connection error?**
```bash
# Check Redis
redis-cli ping

# Verify REDIS_URL in .env
# Format: redis://host:port/0
```

## 📞 Documentation

- **Architecture Questions** → [README.md](README.md)
- **Setup Issues** → [SETUP.md](SETUP.md)
- **Test Questions** → [TESTS.md](TESTS.md)
- **Code Examples** → `tests/` directory

---

**Ready to start?** Follow the 5-minute setup above!

**Need help?** Check the documentation files linked above.

**Questions?** Review test cases in `tests/` for usage examples.
