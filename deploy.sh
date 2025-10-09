#!/bin/bash
# Intelligent Teams Planner v2.0 - Unix/Linux/macOS Deployment Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/scripts/smart-deploy.py"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "❌ Python is not installed or not in PATH"
        exit 1
    fi
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi

# Check if requests module is available for health checks
$PYTHON_CMD -c "import requests" 2>/dev/null || {
    echo "📦 Installing requests module for health checks..."
    $PYTHON_CMD -m pip install requests
}

# Run the smart deployment script
echo "🚀 Starting Intelligent Teams Planner Smart Deployment..."
$PYTHON_CMD "$PYTHON_SCRIPT" "$@"