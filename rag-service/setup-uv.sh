#!/bin/bash

# RAG Service UV Setup Script
# Following CLAUDE.md guidelines for UV package management

set -e  # Exit on any error

echo "🚀 Setting up RAG Service with UV Package Manager"
echo "================================================"

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

# Clean up any existing virtual environment
if [ -d "venv" ]; then
    echo "🧹 Removing existing virtual environment..."
    rm -rf venv
fi

# Create virtual environment using UV
echo "🏗️  Creating virtual environment with UV..."
uv venv venv

# Activate virtual environment
echo "⚡ Activating virtual environment..."
source venv/bin/activate

# Verify we're in the right environment
echo "🔍 Python location: $(which python)"
echo "🔍 Python version: $(python --version)"

# Install dependencies using UV
echo "📥 Installing dependencies with UV..."
if [ -f "requirements.txt" ]; then
    uv pip install -r requirements.txt
else
    echo "❌ requirements.txt not found!"
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
    import fastapi
    print('✅ FastAPI imported successfully')
except ImportError as e:
    print(f'❌ FastAPI import failed: {e}')

try:
    import unstructured
    print('✅ Unstructured imported successfully')
except ImportError as e:
    print(f'❌ Unstructured import failed: {e}')

try:
    import structlog
    print('✅ Structlog imported successfully')
except ImportError as e:
    print(f'❌ Structlog import failed: {e}')
"

echo ""
echo "🎉 RAG Service setup complete!"
echo ""
echo "To use this environment:"
echo "  cd rag-service"
echo "  source venv/bin/activate"
echo ""
echo "To run the service:"
echo "  export PORT=7120"
echo "  export DATABASE_URL=\"postgresql://itp_user:itp_password_2024@localhost:5432/intelligent_teams_planner\""
echo "  export REDIS_URL=\"redis://localhost:6379\""
echo "  export REDIS_PASSWORD=\"redis_password_2024\""
echo "  python -m src.main"
echo ""
echo "To run tests:"
echo "  pytest tests/ -v"
echo ""