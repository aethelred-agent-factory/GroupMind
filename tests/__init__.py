"""pytest configuration for test discovery and execution."""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest_plugins = ["pytest_asyncio"]

# Configure pytest-asyncio
asyncio_mode = "auto"
