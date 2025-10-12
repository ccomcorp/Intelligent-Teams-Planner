#!/bin/bash

# Check Status of Intelligent Teams Planner Infrastructure
# Usage: ./scripts/deployment/status.sh

set -e

echo "📊 Intelligent Teams Planner - Infrastructure Status"
echo "=================================================="

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker is not running"
    exit 1
fi

# Check if services are deployed
if ! docker compose -f docker-compose.simple.yml ps | grep -q "itp-"; then
    echo "❌ No services deployed. Run ./scripts/deployment/deploy-infrastructure.sh first"
    exit 1
fi

echo ""
echo "🐳 Docker Container Status:"
docker compose -f docker-compose.simple.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "🏥 Health Checks:"

# PostgreSQL Health
if docker compose -f docker-compose.simple.yml exec -T postgres pg_isready -U itp_user -d intelligent_teams_planner >/dev/null 2>&1; then
    echo "✅ PostgreSQL - Healthy"
else
    echo "❌ PostgreSQL - Unhealthy"
fi

# Redis Health
if docker compose -f docker-compose.simple.yml exec -T redis redis-cli --raw incr ping >/dev/null 2>&1; then
    echo "✅ Redis - Healthy"
else
    echo "❌ Redis - Unhealthy"
fi

# OpenWebUI Note (separate container)
echo "ℹ️ OpenWebUI - Managed as separate standalone container"

# Neo4j Health
if curl -f http://localhost:7474/ >/dev/null 2>&1; then
    echo "✅ Neo4j - Accessible (http://localhost:7474)"
else
    echo "❌ Neo4j - Not accessible"
fi

echo ""
echo "💾 Resource Usage:"
echo "Docker System Usage:"
docker system df

echo ""
echo "📈 Container Resource Usage:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"

echo ""
echo "🔧 Quick Commands:"
echo "   • View logs:     docker compose -f docker-compose.simple.yml logs -f [service]"
echo "   • Restart all:   ./scripts/deployment/deploy-infrastructure.sh"
echo "   • Stop all:      docker compose -f docker-compose.simple.yml down"
echo "   • Shell access:  docker compose -f docker-compose.simple.yml exec [service] bash"