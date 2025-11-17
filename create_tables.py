#!/usr/bin/env python
"""Create database tables."""

import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from bot.models.database import Base

async def create_tables():
    # Try container hostname first
    urls_to_try = [
        "postgresql+asyncpg://postgres:postgres@groupmind-postgres-1:5432/groupmind",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/groupmind",
        "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/groupmind",
    ]
    
    for database_url in urls_to_try:
        try:
            print(f"🔌 Attempting: {database_url.split('@')[1].split('/')[0]}...")
            engine = create_async_engine(database_url, echo=False)
            async with engine.begin() as conn:
                print("📦 Creating tables...")
                await conn.run_sync(Base.metadata.create_all)
            await engine.dispose()
            print("✅ Tables created successfully")
            return
        except Exception as e:
            print(f"   ❌ Failed: {str(e)[:50]}")
            continue
    
    print("❌ Could not connect to database from any URL")
    sys.exit(1)

if __name__ == "__main__":
    asyncio.run(create_tables())
