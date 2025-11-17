#!/bin/bash
# GroupMind Bot Launcher

set -e

cd /workspaces/GroupMind

echo "🤖 GroupMind Telegram Bot - Starting..."
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Please ensure .env is configured in /workspaces/GroupMind/.env"
    exit 1
fi

# Check if credentials are set
if grep -q "TELEGRAM_BOT_TOKEN=7981793798" .env && grep -q "DEEPSEEK_API_KEY=sk-9aba4ee1fcad449892cb6102f29e7aa7" .env; then
    echo "✅ Credentials configured"
else
    echo "❌ Credentials not found in .env"
    exit 1
fi

echo ""
echo "📋 Services Status:"
echo ""

# Check if Redis is running
if nc -z localhost 6379 2>/dev/null; then
    echo "✅ Redis: Running on localhost:6379"
else
    echo "⚠️  Redis: Not accessible on localhost:6379"
    echo "   Starting Redis via Docker..."
    docker-compose up -d redis
    sleep 2
fi

# Check if PostgreSQL is running
if nc -z localhost 5432 2>/dev/null; then
    echo "✅ PostgreSQL: Running on localhost:5432"
else
    echo "⚠️  PostgreSQL: Not accessible on localhost:5432"
    echo "   Starting PostgreSQL via Docker..."
    docker-compose up -d postgres
    sleep 3
fi

echo ""
echo "🚀 Starting GroupMind Bot..."
echo ""
echo "Bot Token: 7981793798:AAGyeC1OZwhtvSY-BNWCAQ2S1h8IImaTh1U"
echo "DeepSeek Key: sk-9aba4ee1fcad449892cb6102f29e7aa7"
echo ""
echo "Bot is starting... Press Ctrl+C to stop"
echo ""

python bot/main.py
