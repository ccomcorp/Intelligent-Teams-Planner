#!/bin/bash

# OpenWebUI Initialization Script for Intelligent Teams Planner v2.0
# This script configures OpenWebUI on startup

set -e

echo "🚀 Initializing OpenWebUI for Intelligent Teams Planner..."

# Set default environment variables if not provided
export WEBUI_SECRET_KEY=${WEBUI_SECRET_KEY:-"your-secret-key-change-in-production"}
export OPENAI_API_BASE_URL=${OPENAI_API_BASE_URL:-"http://mcpo-proxy:8001/v1"}
export OPENAI_API_KEY=${OPENAI_API_KEY:-"dummy-key"}

# Database configuration
export DATABASE_URL=${DATABASE_URL:-"postgresql://itp_user:itp_password_2024@postgres:5432/intelligent_teams_planner"}

# Enable RAG and vector search
export ENABLE_RAG_WEB_SEARCH=true
export ENABLE_RAG_WEB_LOADER=true
export RAG_EMBEDDING_ENGINE=openai
export RAG_EMBEDDING_MODEL=text-embedding-3-small

# Chunk configuration
export CHUNK_SIZE=1000
export CHUNK_OVERLAP=100

# PDF processing
export PDF_EXTRACT_IMAGES=true

# ChromaDB configuration (fallback if PostgreSQL vector search not available)
export CHROMA_TENANT=default_tenant
export CHROMA_DATABASE=default_database

echo "📋 Configuring Planner-specific settings..."

# Create custom directories
mkdir -p /app/backend/data/uploads
mkdir -p /app/backend/data/cache
mkdir -p /app/backend/data/logs

# Copy custom CSS if it exists
if [ -f "/app/backend/config/custom.css" ]; then
    cp /app/backend/config/custom.css /app/backend/static/css/itp-custom.css
    echo "✅ Custom CSS installed"
fi

# Copy plugin files
if [ -d "/app/backend/config/plugins" ]; then
    cp -r /app/backend/config/plugins/* /app/backend/plugins/
    echo "✅ Plugins installed"
fi

# Set permissions
chown -R 1000:1000 /app/backend/data
chmod -R 755 /app/backend/data

echo "🔧 Testing MCPO Proxy connection..."

# Wait for MCPO Proxy to be available
max_attempts=30
attempt=1

while [ $attempt -le $max_attempts ]; do
    if curl -f -s "http://mcpo-proxy:8001/health" > /dev/null; then
        echo "✅ MCPO Proxy is available"
        break
    else
        echo "⏳ Waiting for MCPO Proxy... (attempt $attempt/$max_attempts)"
        sleep 2
        attempt=$((attempt + 1))
    fi
done

if [ $attempt -gt $max_attempts ]; then
    echo "❌ MCPO Proxy is not available after $max_attempts attempts"
    echo "⚠️  OpenWebUI will start but Planner features may not work"
fi

echo "🔧 Testing database connection..."

# Test database connection
if python3 -c "
import asyncpg
import asyncio
import os

async def test_db():
    try:
        conn = await asyncpg.connect(os.environ['DATABASE_URL'])
        await conn.execute('SELECT 1')
        await conn.close()
        print('✅ Database connection successful')
        return True
    except Exception as e:
        print(f'❌ Database connection failed: {e}')
        return False

result = asyncio.run(test_db())
exit(0 if result else 1)
"; then
    echo "✅ Database is available"
else
    echo "❌ Database connection failed"
    echo "⚠️  OpenWebUI will start but some features may not work"
fi

echo "📦 Installing Python dependencies..."

# Install additional Python packages for Planner integration
pip install --no-cache-dir \
    asyncpg \
    sqlalchemy[asyncio] \
    structlog \
    httpx

echo "🎨 Configuring UI theme..."

# Create custom branding
cat > /app/backend/static/branding.json << EOF
{
  "name": "Intelligent Teams Planner",
  "description": "AI-powered Microsoft Teams Planner management",
  "logo": "/static/images/itp-logo.png",
  "favicon": "/static/images/favicon.ico",
  "theme": {
    "primary": "#0078D4",
    "secondary": "#106EBE",
    "accent": "#5B2C6F"
  }
}
EOF

echo "🔌 Registering plugins..."

# Register Planner Tools plugin
if [ -f "/app/backend/plugins/planner_tools.py" ]; then
    python3 -c "
import sys
sys.path.append('/app/backend/plugins')
try:
    from planner_tools import create_plugin
    plugin = create_plugin()
    print(f'✅ Plugin {plugin.name} v{plugin.version} registered successfully')
except Exception as e:
    print(f'❌ Failed to register plugin: {e}')
"
fi

echo "📋 Creating default model configuration..."

# Create default model configuration for Planner Assistant
cat > /app/backend/data/models.json << EOF
{
  "models": [
    {
      "id": "planner-assistant",
      "name": "Planner Assistant",
      "base_url": "http://mcpo-proxy:8001/v1",
      "api_key": "dummy-key",
      "description": "Microsoft Planner management assistant with natural language interface",
      "capabilities": ["chat", "tools"],
      "default": true,
      "enabled": true,
      "metadata": {
        "provider": "intelligent-teams-planner",
        "version": "2.0.0",
        "supports_tools": true,
        "supports_streaming": false
      }
    }
  ]
}
EOF

echo "🔒 Configuring security settings..."

# Set secure headers and session configuration
export SECURE_HEADERS=true
export SESSION_SECURE=true
export SESSION_HTTPONLY=true
export SESSION_SAMESITE=lax
export SESSION_MAX_AGE=86400

echo "📊 Setting up monitoring..."

# Create health check endpoint script
cat > /app/backend/health_check.py << 'EOF'
import asyncio
import httpx
import json
from datetime import datetime

async def comprehensive_health_check():
    """Comprehensive health check for all services"""

    services = {
        "mcpo_proxy": "http://mcpo-proxy:8001/health",
        "mcp_server": "http://planner-mcp-server:8000/health",
        "postgres": None,  # Will test with connection
        "redis": None      # Will test with connection
    }

    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "services": {}
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Test HTTP services
        for service, url in services.items():
            if url:
                try:
                    response = await client.get(url)
                    results["services"][service] = {
                        "status": "healthy" if response.status_code == 200 else "unhealthy",
                        "response_time": response.elapsed.total_seconds(),
                        "status_code": response.status_code
                    }
                except Exception as e:
                    results["services"][service] = {
                        "status": "unhealthy",
                        "error": str(e)
                    }

    # Test database
    try:
        import asyncpg
        import os
        conn = await asyncpg.connect(os.environ.get('DATABASE_URL'))
        await conn.execute('SELECT 1')
        await conn.close()
        results["services"]["postgres"] = {"status": "healthy"}
    except Exception as e:
        results["services"]["postgres"] = {"status": "unhealthy", "error": str(e)}

    # Test Redis
    try:
        import redis.asyncio as redis
        import os
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
        r = redis.from_url(redis_url)
        await r.ping()
        await r.close()
        results["services"]["redis"] = {"status": "healthy"}
    except Exception as e:
        results["services"]["redis"] = {"status": "unhealthy", "error": str(e)}

    return results

if __name__ == "__main__":
    result = asyncio.run(comprehensive_health_check())
    print(json.dumps(result, indent=2))
EOF

echo "✅ OpenWebUI initialization completed!"
echo ""
echo "🌟 Intelligent Teams Planner v2.0 is ready!"
echo ""
echo "📋 Configuration Summary:"
echo "  • MCPO Proxy: http://mcpo-proxy:8001"
echo "  • MCP Server: http://planner-mcp-server:8000"
echo "  • Database: PostgreSQL with pgvector"
echo "  • Cache: Redis"
echo "  • Primary Model: planner-assistant"
echo ""
echo "🔗 Access URLs:"
echo "  • OpenWebUI: http://localhost:3000"
echo "  • Teams Bot: http://localhost:3978"
echo "  • API Documentation: http://localhost:8001/docs"
echo ""
echo "🚀 Starting OpenWebUI..."