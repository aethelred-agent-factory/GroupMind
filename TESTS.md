# GroupMind Bot - Comprehensive Test Suite

## Overview

The test suite provides comprehensive coverage for the GroupMind Telegram bot, including:
- Command handlers (`/start`, `/summary`, `/help`)
- Message processing and sentiment analysis
- Database models and ORM operations
- Redis rate limiting and job queue
- DeepSeek API integration with fallbacks
- End-to-end workflows and integration tests

## Test Structure

```
tests/
├── __init__.py                 # Test package initialization
├── conftest.py                 # Pytest fixtures and configuration
├── test_handlers.py            # Command and message handlers
├── test_services.py            # Service layer (DeepSeek, sentiment, summarizer)
├── test_models.py              # Database models and utilities
└── test_integration.py         # End-to-end workflows
```

## Running Tests

### Prerequisites

Install test dependencies:
```bash
pip install pytest pytest-asyncio pytest-cov aiosqlite
```

### Run All Tests

```bash
pytest
```

### Run Specific Test File

```bash
pytest tests/test_handlers.py
```

### Run Specific Test Class

```bash
pytest tests/test_handlers.py::TestCommandHandler
```

### Run Specific Test

```bash
pytest tests/test_handlers.py::TestCommandHandler::test_start_command_new_user
```

### Run with Coverage

```bash
pytest --cov=bot --cov-report=html
```

### Run with Verbose Output

```bash
pytest -v
```

### Run Only Async Tests

```bash
pytest -m asyncio
```

### Run Tests in Parallel

```bash
pip install pytest-xdist
pytest -n auto
```

## Test Categories

### Unit Tests
- Individual function/method testing
- Mocked external dependencies
- Fast execution

### Integration Tests
- Multi-component workflows
- Database operations
- Redis operations
- DeepSeek API mocking

### Files Overview

#### `conftest.py` - Shared Fixtures

**Fixtures:**
- `test_db`: In-memory SQLite database for testing
- `mock_redis`: Mocked Redis client
- `mock_telegram_user`: Mock Telegram user object
- `mock_telegram_chat`: Mock Telegram chat object
- `mock_telegram_message`: Mock Telegram message
- `mock_telegram_update`: Mock Telegram update
- `mock_application`: Mock Telegram application
- `mock_context`: Mock Telegram context
- `rate_limiter`: CombinedRateLimiter instance
- `job_queue`: JobQueue instance
- `mock_deepseek_response`: Sample DeepSeek API response
- `mock_deepseek_error_response`: Sample error response

**Helper Functions:**
- `create_test_message()`: Create test message objects
- `create_test_update()`: Create test update objects

#### `test_handlers.py` - Command & Message Handlers

**Test Classes:**
- `TestCommandHandler`: Command execution, authorization, rate limiting
- `TestRedisRateLimiter`: Rate limit checking
- `TestSummaryJobQueue`: Job queue operations
- `TestCommandHandlerErrors`: Error handling
- `TestAuthorizationChecks`: Authorization logic

**Key Tests:**
- `/start` command for new and existing users
- `/help` command
- `/summary` command with rate limiting
- Telegram API error handling
- Redis error handling

#### `test_services.py` - Service Layer

**Test Classes:**
- `TestDeepSeekClient`: DeepSeek API integration
- `TestSentimentAnalyzer`: Sentiment analysis
- `TestSummarizer`: Conversation summarization
- `TestServiceIntegration`: End-to-end service workflows

**Key Tests:**
- Summary generation with DeepSeek
- Retry logic on API failures
- Token counting and context management
- Positive/negative/neutral sentiment detection
- Emotion detection
- Language detection
- Conversation analysis

#### `test_models.py` - Database & Utilities

**Test Classes:**
- `TestDatabaseModels`: ORM model operations
- `TestRateLimiter`: Rate limiting implementations
- `TestJobQueue`: Job queue operations
- `TestDatabaseRelationships`: Model relationships

**Key Tests:**
- Group, User, Message, Summary, AuditLog CRUD
- Soft deletion functionality
- Foreign key relationships
- Rate limiter token bucket algorithm
- Job enqueueing/dequeueing
- Job status tracking

#### `test_integration.py` - End-to-End Workflows

**Test Classes:**
- `TestMessageWorkflow`: Message capture pipeline
- `TestSentimentAnalysisWorkflow`: Sentiment analysis workflows
- `TestCommandRateLimitingWorkflow`: Rate limiting scenarios
- `TestEndToEndWorkflow`: Complete user journeys
- `TestErrorRecovery`: Error handling and fallbacks

**Key Tests:**
- Message to summary pipeline
- User journey from /start to /summary
- DeepSeek failure fallback
- Redis connection failure handling
- Database transaction rollback

## Mocking Strategy

### Redis Mocking
```python
mock_redis.get = AsyncMock(return_value=None)
mock_redis.set = AsyncMock(return_value=True)
mock_redis.incr = AsyncMock(return_value=1)
```

### Telegram Mocking
```python
mock_context.application.bot.send_message = AsyncMock(return_value=None)
```

### DeepSeek API Mocking
```python
mock_response = {
    "choices": [{"message": {"content": "Summary"}}],
    "usage": {"prompt_tokens": 100, "completion_tokens": 50}
}
```

## Database Testing

Tests use in-memory SQLite with the actual SQLAlchemy models:

```python
@pytest.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    # ... create tables and session
    yield session
    # ... cleanup
```

This ensures:
- No external database required
- Fast test execution
- Automatic cleanup between tests
- Same schema as production

## Async Testing

All async code is tested using `pytest-asyncio`:

```python
@pytest.mark.asyncio
async def test_some_async_function():
    result = await some_async_function()
    assert result is not None
```

## Coverage Goals

Target coverage areas:
- **Handlers**: >90% (critical user interaction)
- **Services**: >85% (core business logic)
- **Models**: >90% (data persistence)
- **Utils**: >80% (helper functions)
- **Overall**: >80%

Check coverage:
```bash
pytest --cov=bot --cov-report=term-missing
```

## Best Practices

1. **Use Fixtures**: Leverage `conftest.py` fixtures for common setup
2. **Mock External Services**: Mock Redis, Telegram API, and DeepSeek
3. **Test Async Code**: Use `@pytest.mark.asyncio` for async tests
4. **Database Isolation**: Use in-memory database for fast, isolated tests
5. **Test Errors**: Include tests for error cases and edge conditions
6. **Clear Naming**: Test names clearly describe what they test
7. **Arrange-Act-Assert**: Organize tests with clear AAA pattern

## Continuous Integration

These tests are designed to run in CI/CD pipelines:

```bash
# Run tests with coverage and generate reports
pytest --cov=bot --cov-report=xml --cov-report=term-missing -v
```

## Troubleshooting

### Import Errors
Ensure `/workspaces/GroupMind` is in `PYTHONPATH`:
```bash
export PYTHONPATH=/workspaces/GroupMind:$PYTHONPATH
pytest
```

### Async Warnings
Install `pytest-asyncio`:
```bash
pip install pytest-asyncio
```

### Database Errors
Tests use in-memory SQLite. Ensure `aiosqlite` is installed:
```bash
pip install aiosqlite
```

### Mock Issues
Ensure mock objects are awaitable for async functions:
```python
AsyncMock(return_value=...)  # For async functions
MagicMock(...)               # For sync functions
```

## Future Improvements

- [ ] Add performance benchmarks
- [ ] Add load testing for rate limiter
- [ ] Add database migration tests
- [ ] Add message batch processing tests
- [ ] Add sentiment analysis edge cases
- [ ] Add DeepSeek token overflow handling tests
- [ ] Add concurrent request handling tests
