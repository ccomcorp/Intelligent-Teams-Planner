#!/bin/bash

# Planner MCP Server UV Setup Script
# Following CLAUDE.md guidelines for UV package management
# This service has both Poetry (pyproject.toml) and requirements.txt for UV compatibility

set -e  # Exit on any error

echo "🚀 Setting up Planner MCP Server with UV Package Manager"
echo "======================================================="

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
    import mcp
    print('✅ MCP imported successfully')
except ImportError as e:
    print(f'❌ MCP import failed: {e}')

try:
    import httpx
    print('✅ httpx imported successfully')
except ImportError as e:
    print(f'❌ httpx import failed: {e}')

try:
    import pydantic
    print('✅ pydantic imported successfully')
except ImportError as e:
    print(f'❌ pydantic import failed: {e}')
"

echo ""
echo "🎉 Planner MCP Server UV setup complete!"
echo ""
echo "📝 Note: This project supports both UV and Poetry:"
echo ""
echo "To use UV environment:"
echo "  cd planner-mcp-server"
echo "  source venv-uv/bin/activate"
echo ""
echo "To use Poetry environment (recommended for this project):"
echo "  cd planner-mcp-server"
echo "  poetry shell"
echo ""
echo "To run the MCP server with UV:"
echo "  export PYTHONPATH=/path/to/planner-mcp-server"
echo "  python -m src.main"
echo ""
echo "To run the MCP server with Poetry:"
echo "  poetry run python -m src.main"
echo ""
echo "To run tests:"
echo "  pytest tests/ -v"
echo ""