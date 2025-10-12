#!/bin/bash

# Start Standalone OpenWebUI Container
# This container can be shared across multiple applications

set -e

echo "🚀 Starting Standalone OpenWebUI Container..."

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Stop any existing OpenWebUI container
echo "🧹 Stopping any existing OpenWebUI container..."
docker stop openwebui 2>/dev/null || true
docker rm openwebui 2>/dev/null || true

# Start standalone OpenWebUI container
echo "🌐 Starting OpenWebUI..."
docker run -d \
  --name openwebui \
  -p 7115:8080 \
  -e OPENAI_API_KEY="${OPENAI_API_KEY:-demo-key}" \
  -e OPENAI_API_BASE_URL="${OPENAI_API_BASE_URL:-http://host.docker.internal:7105/v1}" \
  -e WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:-itp-secret-key-2024}" \
  -e ENV=production \
  -v openwebui_data:/app/backend/data \
  --restart unless-stopped \
  ghcr.io/open-webui/open-webui:main

# Wait for container to start
echo "⏳ Waiting for OpenWebUI to initialize..."
sleep 10

# Health check
if curl -f http://localhost:7115/ >/dev/null 2>&1; then
    echo "✅ OpenWebUI is running and accessible!"
    echo ""
    echo "📋 Access Information:"
    echo "   • URL: http://localhost:7115"
    echo "   • Container: openwebui"
    echo "   • Status: Standalone (shared across applications)"
    echo "   • Backend: Connected to MCPO Proxy (localhost:7105)"
    echo ""
    echo "🔧 Management Commands:"
    echo "   • View logs:  docker logs -f openwebui"
    echo "   • Stop:       docker stop openwebui"
    echo "   • Restart:    docker restart openwebui"
    echo "   • Remove:     docker stop openwebui && docker rm openwebui"
else
    echo "⚠️ OpenWebUI is starting... Check logs with: docker logs openwebui"
fi

echo ""
echo "🎉 Standalone OpenWebUI deployment complete!"