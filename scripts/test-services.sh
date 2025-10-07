#!/bin/bash

# Test script for Intelligent Teams Planner MVP services
# This script tests each service health and basic functionality

set -e

echo "🚀 Starting Intelligent Teams Planner MVP Service Tests"
echo "======================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
check_service() {
    local service_name=$1
    local port=$2
    local endpoint=${3:-"/health"}

    echo -n "Testing $service_name on port $port... "

    if curl -f -s "http://localhost:$port$endpoint" > /dev/null; then
        echo -e "${GREEN}✓ PASS${NC}"
        return 0
    else
        echo -e "${RED}✗ FAIL${NC}"
        return 1
    fi
}

test_service_endpoint() {
    local service_name=$1
    local port=$2
    local endpoint=$3
    local method=${4:-"GET"}

    echo -n "Testing $service_name endpoint $endpoint... "

    if curl -f -s -X "$method" "http://localhost:$port$endpoint" > /dev/null; then
        echo -e "${GREEN}✓ PASS${NC}"
        return 0
    else
        echo -e "${RED}✗ FAIL${NC}"
        return 1
    fi
}

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10

echo ""
echo "🔍 Testing Core Infrastructure Services"
echo "======================================"

# Test PostgreSQL
echo -n "Testing PostgreSQL (port 5432)... "
if pg_isready -h localhost -p 5432 -U planner > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
fi

# Test Redis
echo -n "Testing Redis (port 6379)... "
if redis-cli -p 6379 ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
fi

# Test Qdrant
check_service "Qdrant" 6333

# Test Neo4j
echo -n "Testing Neo4j (port 7474)... "
if curl -f -s "http://localhost:7474" > /dev/null; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
fi

echo ""
echo "🧪 Testing Application Services"
echo "==============================="

# Test each microservice
check_service "Planner MCP Server" 8000
check_service "MCPO Proxy" 8001
check_service "RAG Service" 8002
check_service "Graphiti Service" 8003
check_service "Document Generator" 8004
check_service "Web Crawler" 8005

echo ""
echo "📋 Testing Service Functionality"
echo "==============================="

# Test MCP Server endpoints
test_service_endpoint "Planner MCP Server" 8000 "/tools"

# Test MCPO Proxy endpoints
test_service_endpoint "MCPO Proxy" 8001 "/openapi.json"
test_service_endpoint "MCPO Proxy" 8001 "/tools"

# Test RAG Service endpoints
test_service_endpoint "RAG Service" 8002 "/collections"

# Test Graphiti Service endpoints
test_service_endpoint "Graphiti Service" 8003 "/stats"

# Test Document Generator endpoints
test_service_endpoint "Document Generator" 8004 "/templates"

# Test Web Crawler endpoints
test_service_endpoint "Web Crawler" 8005 "/cache/stats"

echo ""
echo "🔗 Testing Service Integration"
echo "============================="

# Test MCPO Proxy can reach MCP Server
echo -n "Testing MCPO Proxy → MCP Server integration... "
if curl -f -s "http://localhost:8001/info" | grep -q "mcp_server"; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
fi

# Test RAG Service can reach Qdrant
echo -n "Testing RAG Service → Qdrant integration... "
if curl -f -s "http://localhost:8002/collections" | grep -q "collections"; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
fi

# Test Graphiti Service can reach Neo4j
echo -n "Testing Graphiti Service → Neo4j integration... "
if curl -f -s "http://localhost:8003/stats" | grep -q "nodes"; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
fi

echo ""
echo "📊 Service Status Summary"
echo "========================"

# Generate comprehensive status report
echo "Generating service status report..."

cat > /tmp/service_status.json << EOF
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "services": {
EOF

services=(
    "postgres:5432"
    "redis:6379"
    "qdrant:6333"
    "neo4j:7474"
    "planner-mcp-server:8000"
    "mcpo-proxy:8001"
    "rag-service:8002"
    "graphiti-service:8003"
    "doc-generator:8004"
    "web-crawler:8005"
)

for i, service in enumerate(services); do
    name=$(echo $service | cut -d: -f1)
    port=$(echo $service | cut -d: -f2)

    if [[ $port == "5432" ]]; then
        if pg_isready -h localhost -p $port -U planner > /dev/null 2>&1; then
            status="healthy"
        else
            status="unhealthy"
        fi
    elif [[ $port == "6379" ]]; then
        if redis-cli -p $port ping > /dev/null 2>&1; then
            status="healthy"
        else
            status="unhealthy"
        fi
    else
        if curl -f -s "http://localhost:$port/health" > /dev/null; then
            status="healthy"
        else
            status="unhealthy"
        fi
    fi

    echo "    \"$name\": \"$status\"$([ $i -lt $((${#services[@]} - 1)) ] && echo ",")" >> /tmp/service_status.json
done

cat >> /tmp/service_status.json << EOF
  }
}
EOF

echo "Service status report saved to: /tmp/service_status.json"

# Display summary
healthy_count=$(grep -o '"healthy"' /tmp/service_status.json | wc -l)
total_count=${#services[@]}

echo ""
echo -e "✅ Healthy Services: ${GREEN}$healthy_count${NC}/$total_count"

if [[ $healthy_count -eq $total_count ]]; then
    echo -e "${GREEN}🎉 All services are running and healthy!${NC}"
    echo ""
    echo "🔧 Next Steps:"
    echo "1. Configure your Microsoft Graph API credentials in .env"
    echo "2. Access MCPO Proxy OpenAPI spec: http://localhost:8001/openapi.json"
    echo "3. Integrate with OpenWebUI using the proxy URL: http://localhost:8001"
    echo "4. Test authentication: http://localhost:8000/auth/login"
else
    echo -e "${YELLOW}⚠️  Some services are not healthy. Check logs for details.${NC}"
    echo ""
    echo "🔍 Troubleshooting:"
    echo "1. Check service logs: docker compose logs [service-name]"
    echo "2. Ensure all required environment variables are set"
    echo "3. Verify network connectivity between services"
fi

echo ""
echo "📖 Documentation:"
echo "- README.md: Project overview and setup instructions"
echo "- docs/prd-mvp.md: Product requirements and user stories"
echo "- docker-compose.yml: Service configuration"
echo ""
echo "🚀 Test completed at $(date)"