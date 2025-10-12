#!/bin/bash

# Deploy Infrastructure for Intelligent Teams Planner
# Usage: ./scripts/deployment/deploy-infrastructure.sh

set -e

echo "🚀 Deploying Intelligent Teams Planner Infrastructure..."

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Clean up previous deployments
echo "🧹 Cleaning up previous deployments..."
docker compose -f docker-compose.simple.yml down --remove-orphans || true

# Clean up Docker system if needed
echo "🗑️ Cleaning up Docker system..."
docker system prune -f >/dev/null 2>&1 || true

# Deploy infrastructure
echo "📦 Deploying infrastructure services..."
docker compose -f docker-compose.simple.yml up -d

# Wait for services to start
echo "⏳ Waiting for services to initialize..."
sleep 15

# Check service status
echo "🔍 Checking service status..."
docker compose -f docker-compose.simple.yml ps

# Health checks
echo "🏥 Running health checks..."

# Check PostgreSQL
if docker compose -f docker-compose.simple.yml exec -T postgres pg_isready -U itp_user -d intelligent_teams_planner >/dev/null 2>&1; then
    echo "✅ PostgreSQL is healthy"
else
    echo "⚠️ PostgreSQL is starting..."
fi

# Check Redis
if docker compose -f docker-compose.simple.yml exec -T redis redis-cli --raw incr ping >/dev/null 2>&1; then
    echo "✅ Redis is healthy"
else
    echo "⚠️ Redis is starting..."
fi

# Note: OpenWebUI runs as separate standalone container
echo "ℹ️ OpenWebUI runs as separate container (not managed by this script)"

# Check Neo4j
if curl -f http://localhost:7474/ >/dev/null 2>&1; then
    echo "✅ Neo4j is accessible at http://localhost:7474"
else
    echo "⚠️ Neo4j is starting..."
fi

echo ""
echo "🎉 Infrastructure deployment complete!"
echo ""
echo "📋 Infrastructure Access Points:"
echo "   • Neo4j:      http://localhost:7474"
echo "   • PostgreSQL: localhost:5432"
echo "   • Redis:      localhost:6379"
echo "   • OpenWebUI:  (Separate standalone container)"
echo ""
echo "📊 Service Status:"
docker compose -f docker-compose.simple.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "🔧 Management Commands:"
echo "   • View logs:  docker compose -f docker-compose.simple.yml logs -f"
echo "   • Stop all:   docker compose -f docker-compose.simple.yml down"
echo "   • Restart:    ./scripts/deployment/deploy-infrastructure.sh"