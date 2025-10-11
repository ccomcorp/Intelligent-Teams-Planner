#!/bin/bash

# Teams Bot UV Setup Script
# Following CLAUDE.md guidelines for UV package management
# This service has both Poetry (pyproject.toml) and requirements.txt for UV compatibility

set -e  # Exit on any error

echo "🚀 Setting up Teams Bot with UV Package Manager"
echo "==============================================="

# Ensure we're in the right directory
cd "$(dirname "$0")"

# Check if UV is installed
if ! command -v uv &> /dev/null; then
    echo "📦 UV not found. Installing UV package manager..."

    # Install UV based on platform
    if [[ "$OSTYPE" == "darwin"* ]] || [[ "$OSTYPE" == "linux-gnu"* ]]; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    else
        echo "❌ Unsupported platform for automatic UV installation"
        echo "Please install UV manually: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
fi

# Verify UV installation
echo "✅ UV version: $(uv --version)"

# Clean up any existing UV virtual environment
if [ -d "venv-uv" ]; then
    echo "🧹 Removing existing UV virtual environment..."
    rm -rf venv-uv
fi

# Create virtual environment using UV
echo "🏗️  Creating UV virtual environment..."
uv venv venv-uv

# Activate virtual environment
echo "⚡ Activating UV virtual environment..."
source venv-uv/bin/activate

# Verify we're in the right environment
echo "🔍 Python location: $(which python)"
echo "🔍 Python version: $(python --version)"

# Install dependencies using UV from requirements.txt
echo "📥 Installing dependencies with UV from requirements.txt..."
if [ -f "requirements.txt" ]; then
    uv pip install -r requirements.txt
else
    echo "❌ requirements.txt not found!"
    echo "Note: This project uses Poetry. You can use Poetry with:"
    echo "  poetry install"
    echo "  poetry shell"
    exit 1
fi

# Verify installation
echo "📋 Installed packages:"
uv pip list

# Test basic imports
echo "🧪 Testing basic imports..."
python -c "
import sys
print(f'Python path: {sys.executable}')

# Test critical imports
try:
    import aiohttp
    print('✅ aiohttp imported successfully')
except ImportError as e:
    print(f'❌ aiohttp import failed: {e}')

try:
    import botbuilder
    print('✅ botbuilder imported successfully')
except ImportError as e:
    print(f'❌ botbuilder import failed: {e}')

try:
    import httpx
    print('✅ httpx imported successfully')
except ImportError as e:
    print(f'❌ httpx import failed: {e}')
"

echo ""
echo "🎉 Teams Bot UV setup complete!"
echo ""
echo "📝 Note: This project supports both UV and Poetry:"
echo ""
echo "To use UV environment:"
echo "  cd teams-bot"
echo "  source venv-uv/bin/activate"
echo ""
echo "To use Poetry environment (recommended for this project):"
echo "  cd teams-bot"
echo "  poetry shell"
echo ""
echo "To run the service with UV:"
echo "  export PORT=7110"
echo "  export BOT_ID=\"test-bot-id\""
echo "  export BOT_PASSWORD=\"test-bot-password\""
echo "  export OPENWEBUI_URL=\"http://localhost:7115\""
echo "  export REDIS_URL=\"redis://localhost:6379\""
echo "  export REDIS_PASSWORD=\"redis_password_2024\""
echo "  python -m src.main"
echo ""
echo "To run the service with Poetry:"
echo "  poetry run python -m src.main"
echo ""
echo "To run tests:"
echo "  pytest tests/ -v"
echo ""