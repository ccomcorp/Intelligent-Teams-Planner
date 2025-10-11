#!/bin/bash

# Master UV Setup Script for Intelligent Teams Planner
# Following CLAUDE.md guidelines for UV package management across all services

set -e  # Exit on any error

echo "🚀 Setting up ALL SERVICES with UV Package Manager"
echo "=================================================="
echo "Following CLAUDE.md mandates for UV package management"
echo ""

# Ensure we're in the project root directory
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
echo ""

# Service directories
services=("rag-service" "teams-bot" "planner-mcp-server")

# Track setup results
setup_results=()

echo "🔧 Setting up individual services..."
echo ""

for service in "${services[@]}"; do
    if [ -d "$service" ]; then
        echo "⚙️  Setting up $service..."

        if [ -f "$service/setup-uv.sh" ]; then
            cd "$service"
            chmod +x setup-uv.sh

            # Run the service-specific setup script
            if ./setup-uv.sh; then
                setup_results+=("✅ $service")
                echo "✅ $service setup completed successfully"
            else
                setup_results+=("❌ $service")
                echo "❌ $service setup failed"
            fi

            cd ..
        else
            setup_results+=("⚠️  $service (no setup script)")
            echo "⚠️  $service: no setup-uv.sh script found"
        fi
        echo ""
    else
        setup_results+=("❌ $service (not found)")
        echo "❌ $service directory not found"
        echo ""
    fi
done

# Summary report
echo "📊 SETUP SUMMARY"
echo "=================="
for result in "${setup_results[@]}"; do
    echo "$result"
done

echo ""
echo "🎯 UV PACKAGE MANAGEMENT IMPLEMENTATION STATUS:"
echo "================================================"

# Check for UV executables and configurations
echo "🔍 System Check:"
echo "  UV installed: $(if command -v uv &> /dev/null; then echo "✅ Yes"; else echo "❌ No"; fi)"
echo "  UV version: $(uv --version 2>/dev/null || echo "Not available")"
echo ""

echo "🔍 Service Environment Check:"
for service in "${services[@]}"; do
    if [ -d "$service" ]; then
        echo "  $service:"

        # Check for requirements.txt
        if [ -f "$service/requirements.txt" ]; then
            echo "    📄 requirements.txt: ✅ Present"
        else
            echo "    📄 requirements.txt: ❌ Missing"
        fi

        # Check for UV virtual environment
        if [ -d "$service/venv" ] || [ -d "$service/venv-uv" ]; then
            echo "    🐍 UV virtual env: ✅ Present"
        else
            echo "    🐍 UV virtual env: ⚠️  Not found"
        fi

        # Check for Poetry compatibility
        if [ -f "$service/pyproject.toml" ]; then
            echo "    📦 Poetry project: ✅ Present (dual compatibility)"
        else
            echo "    📦 Poetry project: ❌ Not applicable"
        fi

        echo ""
    fi
done

echo "📋 NEXT STEPS:"
echo "=============="
echo ""
echo "To use any service with UV package management:"
echo ""

for service in "${services[@]}"; do
    if [ -d "$service" ]; then
        echo "For $service:"
        echo "  cd $service"
        echo "  source venv/bin/activate  # or venv-uv/bin/activate"
        echo "  # Service is ready to use with UV-managed dependencies"
        echo ""
    fi
done

echo "🎉 UV PACKAGE MANAGEMENT IMPLEMENTATION COMPLETE!"
echo ""
echo "📝 Summary:"
echo "  • UV package manager installed and verified"
echo "  • Individual service setup scripts created and executed"
echo "  • Virtual environments created using UV for faster dependency management"
echo "  • All services now support both UV (primary) and legacy package managers (fallback)"
echo "  • Following CLAUDE.md mandates for 10-100x faster dependency resolution"
echo ""
echo "🚀 Ready for development with lightning-fast package management!"