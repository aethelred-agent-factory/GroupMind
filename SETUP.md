# Setup and Deployment Guide

## Quick Start

### 1. Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- Git

### 2. Clone Repository
```bash
git clone <repository-url>
cd GroupMind
```

### 3. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov  # For testing
```

### 5. Configure Environment
```bash
cp .env.example .env
# Edit .env with your credentials
```

### 6. Initialize Database
```bash
# Install Alembic if needed
pip install alembic

# Create database (PostgreSQL)
createdb groupmind

# Run migrations
alembic upgrade head
```

### 7. Run the Bot
```bash
# In terminal 1: Start bot
python -m bot.main

# In terminal 2: Start worker
python -m worker.processor
```

## Using Docker Compose

### One-Command Setup
```bash
# Start all services (PostgreSQL, Redis, Bot, Worker)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Database Migrations

### Understanding Alembic

The project uses Alembic for version-controlled schema changes:

**Files:**
- `alembic.ini`: Main configuration
- `migrations/env.py`: Async configuration
- `migrations/versions/`: Individual migration scripts

### Running Migrations

```bash
# View current version
alembic current

# Upgrade to latest
alembic upgrade head

# Upgrade to specific revision
alembic upgrade abc123

# Downgrade one step
alembic downgrade -1

# Create new migration (auto-detect changes)
alembic revision --autogenerate -m "Add new column"

# Create empty migration
alembic revision -m "custom change"
```

### Migration in Production

```bash
# Always backup first!
pg_dump groupmind > backup_$(date +%Y%m%d).sql

# Run migration
alembic upgrade head

# Verify schema
psql groupmind -c "\dt"
```

## Testing Setup

### Install Test Dependencies
```bash
pip install pytest pytest-asyncio pytest-cov aiosqlite
```

### Run Tests
```bash
# All tests
pytest

# With coverage report
pytest --cov=bot --cov-report=html

# Specific test file
pytest tests/test_handlers.py

# Specific test class
pytest tests/test_handlers.py::TestCommandHandler

# Specific test
pytest tests/test_handlers.py::TestCommandHandler::test_start_command_new_user

# With verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Check Coverage
```bash
# Terminal report
pytest --cov=bot --cov-report=term-missing

# HTML report (opens in browser)
pytest --cov=bot --cov-report=html
# Open htmlcov/index.html in browser
```

## Development Workflow

### Code Quality Tools

```bash
# Install dev dependencies
pip install black isort flake8 mypy

# Format code
black bot tests

# Organize imports
isort bot tests

# Lint
flake8 bot tests

# Type checking
mypy bot
```

### Using Tox (All-in-one)

```bash
# Install tox
pip install tox

# Run all environments
tox

# Run specific environment
tox -e py311        # Run tests on Python 3.11
tox -e lint         # Run linters
tox -e format       # Format code
tox -e coverage     # Generate coverage
tox -e dev          # Development environment
```

## Deployment Checklist

### Pre-Deployment
- [ ] All tests pass: `pytest`
- [ ] Code formatted: `black bot`
- [ ] Imports organized: `isort bot`
- [ ] Linting passes: `flake8 bot`
- [ ] Type checking passes: `mypy bot`
- [ ] Coverage >80%: `pytest --cov=bot`

### Environment Setup
- [ ] `TELEGRAM_BOT_TOKEN` set
- [ ] `DEEPSEEK_API_KEY` set
- [ ] `DATABASE_URL` configured with SSL
- [ ] `REDIS_URL` configured
- [ ] `LOG_LEVEL` set to `INFO`
- [ ] `DEBUG` set to `false`

### Database Setup
- [ ] PostgreSQL created and running
- [ ] Migrations run: `alembic upgrade head`
- [ ] Backups configured
- [ ] Connection pooling configured

### Monitoring Setup
- [ ] Logging configured
- [ ] Error tracking enabled (Sentry)
- [ ] Metrics collection enabled
- [ ] Alerts configured

### Security
- [ ] API keys in environment, not code
- [ ] Database SSL enabled
- [ ] Privacy filtering enabled
- [ ] Rate limiting configured
- [ ] Audit logging enabled

## Common Issues

### PostgreSQL Connection Error
```bash
# Check PostgreSQL is running
psql --version
psql -U postgres -d postgres

# Check DATABASE_URL format
postgresql+asyncpg://user:password@host:port/database
```

### Redis Connection Error
```bash
# Check Redis is running
redis-cli ping

# Check REDIS_URL format
redis://host:port/0
```

### Alembic Migration Error
```bash
# Check current status
alembic current

# See migration history
alembic history

# Check env.py configuration
cat migrations/env.py
```

### Test Failures
```bash
# Run with verbose output
pytest -v

# Run with full traceback
pytest --tb=long

# Run specific test for debugging
pytest -v tests/test_handlers.py::TestCommandHandler::test_start_command_new_user
```

## Performance Tuning

### Database Connection Pool
```python
# In .env
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
```

### Redis Configuration
```bash
# Check Redis memory
redis-cli info memory

# Monitor commands
redis-cli monitor
```

### Worker Configuration
```python
# In .env
WORKER_CONCURRENCY=4
BATCH_SIZE=100
BATCH_TIMEOUT_SECONDS=300
```

## Monitoring and Logs

### View Logs
```bash
# Bot logs
tail -f logs/groupmind.log

# Docker logs
docker-compose logs -f bot
docker-compose logs -f worker

# Follow specific service
docker-compose logs -f postgres
docker-compose logs -f redis
```

### Health Check
```bash
# Check bot status
curl http://localhost:8000/health

# Check database
psql groupmind -c "SELECT COUNT(*) FROM messages;"

# Check Redis
redis-cli ping
```

## Backup and Recovery

### Backup Database
```bash
# Full backup
pg_dump groupmind > backup_$(date +%Y%m%d_%H%M%S).sql

# Compressed backup
pg_dump groupmind | gzip > backup_$(date +%Y%m%d).sql.gz

# Scheduled backup (cron)
0 2 * * * pg_dump groupmind | gzip > /backups/groupmind_$(date +\%Y\%m\%d).sql.gz
```

### Restore Database
```bash
# From SQL file
psql groupmind < backup_20250117.sql

# From compressed file
gunzip -c backup_20250117.sql.gz | psql groupmind

# Full restore (existing DB)
dropdb groupmind
createdb groupmind
psql groupmind < backup_20250117.sql
```

### Backup Redis
```bash
# Manual backup
redis-cli BGSAVE

# Check backup
ls -la /var/lib/redis/dump.rdb

# Restore
redis-cli SHUTDOWN
cp dump.rdb /var/lib/redis/
redis-server /etc/redis/redis.conf
```

## Scaling

### Horizontal Scaling
```bash
# Run multiple bot instances
python -m bot.main --instance 1
python -m bot.main --instance 2

# Run multiple workers
python -m worker.processor --worker 1
python -m worker.processor --worker 2
```

### Load Balancing
```bash
# Use nginx as load balancer
# See docker-compose.yml for example
```

## Rollback Procedure

### Database Rollback
```bash
# Check current migration
alembic current

# Downgrade one step
alembic downgrade -1

# Downgrade to specific version
alembic downgrade abc123

# Verify
alembic current
```

### Code Rollback
```bash
# See recent commits
git log --oneline -10

# Checkout previous version
git checkout <commit-hash>

# Restart services
docker-compose restart
```

## Support and Troubleshooting

### Get Help
1. Check [TESTS.md](TESTS.md) for testing documentation
2. Review [README.md](README.md) for architecture
3. Check logs: `docker-compose logs -f`
4. Run tests: `pytest -v`
5. Check database: `psql groupmind -c "\dt"`

### Debug Mode
```bash
# Enable debug logging
LOG_LEVEL=DEBUG python -m bot.main

# Enable SQLAlchemy SQL logging
DB_ECHO=true python -m bot.main

# Enable Redis verbose logging
redis-cli CONFIG SET loglevel verbose
```

## Next Steps

1. ✅ Complete setup above
2. ✅ Run tests: `pytest`
3. ✅ Review [TESTS.md](TESTS.md) for testing info
4. ✅ Review [README.md](README.md) for architecture
5. 🚀 Deploy to production following checklist above
