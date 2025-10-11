# Intelligent Teams Planner - Microservices Dockerization Blueprint

## Executive Summary

This comprehensive dockerization plan transforms the Intelligent Teams Planner from a monolithic architecture to a robust microservices framework optimized for scalability, maintainability, and deployment flexibility. The analysis reveals a well-structured foundation ready for containerization with strategic enhancements.

## Current Architecture Analysis

### Service Inventory and Communication Flow

```mermaid
graph TB
    Users[Microsoft Teams Users] --> TeamsBot[Teams Bot :7110]
    Users --> OpenWebUI[OpenWebUI :7115]

    TeamsBot --> OpenWebUI
    OpenWebUI --> MCPOProxy[MCPO Proxy :7105]
    MCPOProxy --> MCPServer[MCP Server :7100]

    MCPServer --> GraphAPI[Microsoft Graph API]
    MCPServer --> PostgresDB[(PostgreSQL :5432)]
    MCPServer --> RedisCache[(Redis :6379)]
    MCPServer --> Neo4j[(Neo4j :7474/7687)]

    RAGService[RAG Service :7120] --> PostgresDB
    RAGService --> RedisCache
    RAGService --> OpenWebUI

    subgraph "External Dependencies"
        GraphAPI
        AzureAD[Azure AD]
    end

    subgraph "Data Layer"
        PostgresDB
        RedisCache
        Neo4j
    end
```

### Current Service Portfolio

| Service | Port | Role | Dependencies | Current State |
|---------|------|------|-------------|---------------|
| **MCP Server** | 7100 | Core business logic, Graph API integration | PostgreSQL, Redis, Azure AD | ✅ Dockerized |
| **MCPO Proxy** | 7105 | Protocol translation (OpenWebUI ↔ MCP) | MCP Server, Redis | ✅ Dockerized |
| **Teams Bot** | 7110 | Microsoft Teams client interface | OpenWebUI, Redis, Bot Framework | ✅ Dockerized |
| **OpenWebUI** | 7115 | Central conversational hub | MCPO Proxy | ✅ External Image |
| **RAG Service** | 7120 | Document processing, semantic search | PostgreSQL, Redis, ML models | ✅ Dockerized |
| **PostgreSQL** | 5432 | Primary database with pgvector | None | ✅ External Image |
| **Redis** | 6379 | Caching and session management | None | ✅ External Image |
| **Neo4j** | 7474/7687 | Knowledge graph database | None | ✅ External Image |

## Microservices Architecture Blueprint

### Domain-Driven Service Boundaries

#### 1. **Authentication & Authorization Service**
- **Current**: Embedded in MCP Server
- **Proposed**: Extract to dedicated service
- **Responsibilities**: OAuth flows, token management, user sessions
- **Benefits**: Centralized security, easier compliance, scalable auth

#### 2. **Graph API Gateway Service**
- **Current**: Embedded in MCP Server
- **Proposed**: Extract to dedicated service
- **Responsibilities**: Microsoft Graph API integration, rate limiting, caching
- **Benefits**: API encapsulation, better error handling, independent scaling

#### 3. **Workflow & Task Management Service**
- **Current**: Part of MCP Server
- **Proposed**: Extract core business logic
- **Responsibilities**: Planner operations, task management, business rules
- **Benefits**: Domain focus, easier testing, independent deployment

#### 4. **Communication Hub Service**
- **Current**: Distributed across Teams Bot and MCPO Proxy
- **Proposed**: Centralized message routing
- **Responsibilities**: Multi-channel communication, message routing, protocol translation
- **Benefits**: Unified messaging, easier channel addition, better observability

### Recommended Service Decomposition

```mermaid
graph TB
    subgraph "API Gateway Layer"
        Gateway[API Gateway/Load Balancer]
    end

    subgraph "Application Services"
        AuthService[Auth Service :8001]
        GraphGateway[Graph Gateway :8002]
        WorkflowService[Workflow Service :8003]
        CommHub[Communication Hub :8004]
        RAGService[RAG Service :8005]
        NotificationService[Notification Service :8006]
        AuditService[Audit Service :8007]
    end

    subgraph "Interface Layer"
        TeamsAdapter[Teams Adapter :8010]
        WebUIAdapter[WebUI Adapter :8011]
        APIAdapter[REST API Adapter :8012]
    end

    subgraph "Data Layer"
        PostgresMain[(PostgreSQL Main)]
        PostgresReplica[(PostgreSQL Replica)]
        RedisCluster[(Redis Cluster)]
        Neo4jCluster[(Neo4j Cluster)]
        MinIO[(MinIO/S3)]
    end

    Gateway --> AuthService
    Gateway --> TeamsAdapter
    Gateway --> WebUIAdapter
    Gateway --> APIAdapter

    TeamsAdapter --> CommHub
    WebUIAdapter --> CommHub
    APIAdapter --> CommHub

    CommHub --> WorkflowService
    CommHub --> RAGService
    CommHub --> NotificationService

    AuthService --> WorkflowService
    WorkflowService --> GraphGateway
    WorkflowService --> AuditService

    All Services --> PostgresMain
    All Services --> RedisCluster
    RAGService --> Neo4jCluster
    RAGService --> MinIO
```

## Docker Containerization Strategy

### Base Image Strategy

#### Python Services Base Image
```dockerfile
# Base image for all Python services
FROM python:3.11-slim as python-base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install UV package manager
RUN pip install uv==0.4.18

# Set up application user
RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app
RUN chown -R appuser:appuser /app
USER appuser

# Environment configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_CACHE_DIR=/tmp/uv-cache \
    PATH="/home/appuser/.local/bin:$PATH"
```

#### Multi-Stage Build Pattern
```dockerfile
FROM python-base as builder

# Copy dependency files
COPY requirements.txt pyproject.toml ./

# Install dependencies using UV
RUN uv pip install --system -r requirements.txt

FROM python-base as runtime

# Copy installed packages
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ ./src/
COPY README.md ./

# Health check configuration
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Security hardening
RUN find /app -type f -name "*.py" -exec chmod 644 {} \; \
    && find /app -type d -exec chmod 755 {} \;

# Run application
CMD ["uv", "run", "python", "-m", "src.main"]
```

### Service-Specific Dockerfiles

#### Enhanced MCP Server Dockerfile
```dockerfile
FROM python-base as mcp-server

# Install additional dependencies for Graph API
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && update-ca-certificates

# Copy and install dependencies
COPY requirements.txt pyproject.toml ./
RUN uv pip install --system -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY migrations/ ./migrations/

# Create necessary directories
RUN mkdir -p logs cache temp \
    && chmod 755 logs cache temp

# Environment variables
ENV PORT=8001 \
    PYTHONPATH=/app \
    LOG_LEVEL=INFO

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

#### RAG Service with ML Dependencies
```dockerfile
FROM python:3.11-slim as rag-service

# Install system dependencies for ML libraries
RUN apt-get update && apt-get install -y \
    curl \
    libpq-dev \
    gcc \
    g++ \
    libhdf5-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install UV
RUN pip install uv==0.4.18

# Set up user and directories
RUN useradd --create-home --shell /bin/bash raguser
WORKDIR /app
RUN chown -R raguser:raguser /app
USER raguser

# Copy dependencies
COPY requirements.txt pyproject.toml ./

# Install Python dependencies
RUN uv pip install --system -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY models/ ./models/

# Create model cache directory
RUN mkdir -p /app/model_cache \
    && chmod 755 /app/model_cache

# Environment configuration
ENV PORT=8005 \
    MODEL_CACHE_DIR=/app/model_cache \
    TRANSFORMERS_CACHE=/app/model_cache \
    HF_HOME=/app/model_cache

EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8005/health || exit 1

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8005"]
```

## Docker Compose Orchestration

### Production-Ready Docker Compose

```yaml
version: '3.8'

x-logging: &logging
  logging:
    driver: "json-file"
    options:
      max-size: "10m"
      max-file: "3"

x-restart-policy: &restart-policy
  restart: unless-stopped

x-healthcheck-defaults: &healthcheck-defaults
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s

services:
  # =============================================================================
  # DATA LAYER
  # =============================================================================

  postgres-primary:
    image: pgvector/pgvector:pg16
    container_name: itp-postgres-primary
    environment:
      POSTGRES_DB: intelligent_teams_planner
      POSTGRES_USER: itp_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_REPLICATION_USER: replicator
      POSTGRES_REPLICATION_PASSWORD: ${POSTGRES_REPLICATION_PASSWORD}
      POSTGRES_INITDB_ARGS: "--auth-host=scram-sha-256"
    volumes:
      - postgres_primary_data:/var/lib/postgresql/data
      - ./database/init:/docker-entrypoint-initdb.d
      - ./database/config/primary.conf:/etc/postgresql/postgresql.conf
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U itp_user -d intelligent_teams_planner"]
      <<: *healthcheck-defaults
    networks:
      - itp-backend
    <<: [*logging, *restart-policy]

  postgres-replica:
    image: pgvector/pgvector:pg16
    container_name: itp-postgres-replica
    environment:
      POSTGRES_USER: itp_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_PRIMARY_HOST: postgres-primary
      POSTGRES_REPLICATION_USER: replicator
      POSTGRES_REPLICATION_PASSWORD: ${POSTGRES_REPLICATION_PASSWORD}
    volumes:
      - postgres_replica_data:/var/lib/postgresql/data
      - ./database/config/replica.conf:/etc/postgresql/postgresql.conf
    depends_on:
      postgres-primary:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U itp_user"]
      <<: *healthcheck-defaults
    networks:
      - itp-backend
    <<: [*logging, *restart-policy]

  redis-primary:
    image: redis:7-alpine
    container_name: itp-redis-primary
    command: redis-server /etc/redis/redis.conf
    volumes:
      - redis_primary_data:/data
      - ./redis/config/primary.conf:/etc/redis/redis.conf
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      <<: *healthcheck-defaults
    networks:
      - itp-backend
    <<: [*logging, *restart-policy]

  redis-replica:
    image: redis:7-alpine
    container_name: itp-redis-replica
    command: redis-server /etc/redis/redis.conf
    volumes:
      - redis_replica_data:/data
      - ./redis/config/replica.conf:/etc/redis/redis.conf
    depends_on:
      redis-primary:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      <<: *healthcheck-defaults
    networks:
      - itp-backend
    <<: [*logging, *restart-policy]

  neo4j:
    image: neo4j:5.15-community
    container_name: itp-neo4j
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
      NEO4J_PLUGINS: '["apoc","graph-data-science"]'
      NEO4J_apoc_export_file_enabled: "true"
      NEO4J_apoc_import_file_enabled: "true"
      NEO4J_ACCEPT_LICENSE_AGREEMENT: "yes"
      NEO4J_server_memory_heap_initial__size: "1G"
      NEO4J_server_memory_heap_max__size: "2G"
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - neo4j_import:/var/lib/neo4j/import
      - neo4j_plugins:/plugins
    healthcheck:
      test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "${NEO4J_PASSWORD}", "RETURN 1"]
      <<: *healthcheck-defaults
    networks:
      - itp-backend
    <<: [*logging, *restart-policy]

  minio:
    image: minio/minio:latest
    container_name: itp-minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ACCESS_KEY}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY}
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"
      - "9001:9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      <<: *healthcheck-defaults
    networks:
      - itp-backend
    <<: [*logging, *restart-policy]

  # =============================================================================
  # APPLICATION SERVICES
  # =============================================================================

  auth-service:
    build:
      context: ./services/auth-service
      dockerfile: Dockerfile
    container_name: itp-auth-service
    environment:
      PORT: 8001
      DATABASE_URL: postgresql+asyncpg://itp_user:${POSTGRES_PASSWORD}@postgres-primary:5432/intelligent_teams_planner
      REDIS_URL: redis://redis-primary:6379
      MICROSOFT_CLIENT_ID: ${MICROSOFT_CLIENT_ID}
      MICROSOFT_CLIENT_SECRET: ${MICROSOFT_CLIENT_SECRET}
      MICROSOFT_TENANT_ID: ${MICROSOFT_TENANT_ID}
      JWT_SECRET: ${JWT_SECRET}
      ENCRYPTION_KEY: ${ENCRYPTION_KEY}
    depends_on:
      postgres-primary:
        condition: service_healthy
      redis-primary:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      <<: *healthcheck-defaults
    networks:
      - itp-backend
      - itp-frontend
    <<: [*logging, *restart-policy]

  graph-gateway:
    build:
      context: ./services/graph-gateway
      dockerfile: Dockerfile
    container_name: itp-graph-gateway
    environment:
      PORT: 8002
      AUTH_SERVICE_URL: http://auth-service:8001
      REDIS_URL: redis://redis-primary:6379
      MICROSOFT_GRAPH_API_URL: https://graph.microsoft.com
      RATE_LIMIT_REQUESTS: 1000
      RATE_LIMIT_WINDOW: 3600
    depends_on:
      auth-service:
        condition: service_healthy
      redis-primary:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      <<: *healthcheck-defaults
    networks:
      - itp-backend
    <<: [*logging, *restart-policy]

  workflow-service:
    build:
      context: ./services/workflow-service
      dockerfile: Dockerfile
    container_name: itp-workflow-service
    environment:
      PORT: 8003
      DATABASE_URL: postgresql+asyncpg://itp_user:${POSTGRES_PASSWORD}@postgres-primary:5432/intelligent_teams_planner
      REDIS_URL: redis://redis-primary:6379
      AUTH_SERVICE_URL: http://auth-service:8001
      GRAPH_GATEWAY_URL: http://graph-gateway:8002
      AUDIT_SERVICE_URL: http://audit-service:8007
    depends_on:
      postgres-primary:
        condition: service_healthy
      auth-service:
        condition: service_healthy
      graph-gateway:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8003/health"]
      <<: *healthcheck-defaults
    networks:
      - itp-backend
    <<: [*logging, *restart-policy]

  communication-hub:
    build:
      context: ./services/communication-hub
      dockerfile: Dockerfile
    container_name: itp-communication-hub
    environment:
      PORT: 8004
      REDIS_URL: redis://redis-primary:6379
      WORKFLOW_SERVICE_URL: http://workflow-service:8003
      RAG_SERVICE_URL: http://rag-service:8005
      NOTIFICATION_SERVICE_URL: http://notification-service:8006
    depends_on:
      workflow-service:
        condition: service_healthy
      rag-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8004/health"]
      <<: *healthcheck-defaults
    networks:
      - itp-backend
      - itp-frontend
    <<: [*logging, *restart-policy]

  rag-service:
    build:
      context: ./services/rag-service
      dockerfile: Dockerfile
    container_name: itp-rag-service
    environment:
      PORT: 8005
      DATABASE_URL: postgresql+asyncpg://itp_user:${POSTGRES_PASSWORD}@postgres-primary:5432/intelligent_teams_planner
      REDIS_URL: redis://redis-primary:6379
      NEO4J_URL: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: ${NEO4J_PASSWORD}
      MINIO_ENDPOINT: minio:9000
      MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY}
      MINIO_SECRET_KEY: ${MINIO_SECRET_KEY}
      MODEL_CACHE_DIR: /app/model_cache
    volumes:
      - rag_model_cache:/app/model_cache
    depends_on:
      postgres-primary:
        condition: service_healthy
      neo4j:
        condition: service_healthy
      minio:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8005/health"]
      interval: 45s
      timeout: 15s
      retries: 3
      start_period: 120s
    networks:
      - itp-backend
    <<: [*logging, *restart-policy]

  notification-service:
    build:
      context: ./services/notification-service
      dockerfile: Dockerfile
    container_name: itp-notification-service
    environment:
      PORT: 8006
      REDIS_URL: redis://redis-primary:6379
      EMAIL_SMTP_HOST: ${EMAIL_SMTP_HOST}
      EMAIL_SMTP_PORT: ${EMAIL_SMTP_PORT}
      EMAIL_USERNAME: ${EMAIL_USERNAME}
      EMAIL_PASSWORD: ${EMAIL_PASSWORD}
      TEAMS_WEBHOOK_URL: ${TEAMS_WEBHOOK_URL}
    depends_on:
      redis-primary:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8006/health"]
      <<: *healthcheck-defaults
    networks:
      - itp-backend
    <<: [*logging, *restart-policy]

  audit-service:
    build:
      context: ./services/audit-service
      dockerfile: Dockerfile
    container_name: itp-audit-service
    environment:
      PORT: 8007
      DATABASE_URL: postgresql+asyncpg://itp_user:${POSTGRES_PASSWORD}@postgres-primary:5432/intelligent_teams_planner
      REDIS_URL: redis://redis-primary:6379
      LOG_RETENTION_DAYS: 90
      COMPLIANCE_MODE: enabled
    depends_on:
      postgres-primary:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8007/health"]
      <<: *healthcheck-defaults
    networks:
      - itp-backend
    <<: [*logging, *restart-policy]

  # =============================================================================
  # INTERFACE LAYER
  # =============================================================================

  teams-adapter:
    build:
      context: ./adapters/teams-adapter
      dockerfile: Dockerfile
    container_name: itp-teams-adapter
    environment:
      PORT: 8010
      BOT_ID: ${BOT_ID}
      BOT_PASSWORD: ${BOT_PASSWORD}
      COMMUNICATION_HUB_URL: http://communication-hub:8004
      REDIS_URL: redis://redis-primary:6379
    depends_on:
      communication-hub:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8010/health"]
      <<: *healthcheck-defaults
    networks:
      - itp-frontend
    ports:
      - "8010:8010"
    <<: [*logging, *restart-policy]

  webui-adapter:
    build:
      context: ./adapters/webui-adapter
      dockerfile: Dockerfile
    container_name: itp-webui-adapter
    environment:
      PORT: 8011
      COMMUNICATION_HUB_URL: http://communication-hub:8004
      REDIS_URL: redis://redis-primary:6379
    depends_on:
      communication-hub:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8011/health"]
      <<: *healthcheck-defaults
    networks:
      - itp-frontend
    <<: [*logging, *restart-policy]

  api-adapter:
    build:
      context: ./adapters/api-adapter
      dockerfile: Dockerfile
    container_name: itp-api-adapter
    environment:
      PORT: 8012
      COMMUNICATION_HUB_URL: http://communication-hub:8004
      AUTH_SERVICE_URL: http://auth-service:8001
      RATE_LIMIT_REQUESTS: 1000
      RATE_LIMIT_WINDOW: 3600
    depends_on:
      communication-hub:
        condition: service_healthy
      auth-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8012/health"]
      <<: *healthcheck-defaults
    networks:
      - itp-frontend
    ports:
      - "8012:8012"
    <<: [*logging, *restart-policy]

  # =============================================================================
  # FRONTEND SERVICES
  # =============================================================================

  openwebui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: itp-openwebui
    environment:
      OPENAI_API_BASE_URL: http://webui-adapter:8011/v1
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      WEBUI_SECRET_KEY: ${WEBUI_SECRET_KEY}
      ENV: production
    volumes:
      - openwebui_data:/app/backend/data
    ports:
      - "3000:8080"
    depends_on:
      webui-adapter:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/"]
      <<: *healthcheck-defaults
    networks:
      - itp-frontend
    <<: [*logging, *restart-policy]

  # =============================================================================
  # INFRASTRUCTURE SERVICES
  # =============================================================================

  nginx:
    image: nginx:alpine
    container_name: itp-nginx
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/conf.d:/etc/nginx/conf.d
      - ./ssl:/etc/nginx/ssl
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - openwebui
      - teams-adapter
      - api-adapter
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost/health"]
      <<: *healthcheck-defaults
    networks:
      - itp-frontend
    <<: [*logging, *restart-policy]

  prometheus:
    image: prom/prometheus:latest
    container_name: itp-prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:9090/-/healthy"]
      <<: *healthcheck-defaults
    networks:
      - itp-backend
    <<: [*logging, *restart-policy]

  grafana:
    image: grafana/grafana:latest
    container_name: itp-grafana
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}
      GF_SECURITY_ADMIN_USER: admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
    ports:
      - "3001:3000"
    depends_on:
      - prometheus
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:3000/api/health"]
      <<: *healthcheck-defaults
    networks:
      - itp-backend
    <<: [*logging, *restart-policy]

# =============================================================================
# NETWORKS
# =============================================================================

networks:
  itp-frontend:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/24
  itp-backend:
    driver: bridge
    ipam:
      config:
        - subnet: 172.21.0.0/24

# =============================================================================
# VOLUMES
# =============================================================================

volumes:
  # Database volumes
  postgres_primary_data:
    driver: local
  postgres_replica_data:
    driver: local
  redis_primary_data:
    driver: local
  redis_replica_data:
    driver: local
  neo4j_data:
    driver: local
  neo4j_logs:
    driver: local
  neo4j_import:
    driver: local
  neo4j_plugins:
    driver: local

  # Application volumes
  rag_model_cache:
    driver: local
  minio_data:
    driver: local
  openwebui_data:
    driver: local

  # Monitoring volumes
  prometheus_data:
    driver: local
  grafana_data:
    driver: local
```

## Development vs Production Configurations

### Development Docker Compose Override

```yaml
# docker-compose.dev.yml
version: '3.8'

services:
  # Simplified single-instance databases for development
  postgres-primary:
    ports:
      - "5432:5432"
    environment:
      POSTGRES_PASSWORD: dev_password_123
    volumes:
      - postgres_dev_data:/var/lib/postgresql/data

  redis-primary:
    ports:
      - "6379:6379"
    command: redis-server --requirepass dev_redis_123

  # Development service overrides
  auth-service:
    build:
      context: ./services/auth-service
      dockerfile: Dockerfile.dev
    environment:
      LOG_LEVEL: DEBUG
      TESTING_MODE: "true"
    volumes:
      - ./services/auth-service/src:/app/src:ro
    command: ["uv", "run", "uvicorn", "src.main:app", "--reload", "--host", "0.0.0.0", "--port", "8001"]

  # Remove production-only services
  postgres-replica: null
  redis-replica: null
  nginx: null
  prometheus: null
  grafana: null

volumes:
  postgres_dev_data:
    driver: local
```

## Deployment Strategies

### Rolling Deployment Strategy

```bash
#!/bin/bash
# deploy.sh - Rolling deployment script

set -e

SERVICES=("auth-service" "graph-gateway" "workflow-service" "communication-hub" "rag-service")
COMPOSE_FILE="docker-compose.yml"
BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"

# Create backup
echo "Creating backup..."
mkdir -p "$BACKUP_DIR"
docker-compose exec postgres-primary pg_dump -U itp_user intelligent_teams_planner > "$BACKUP_DIR/database.sql"

# Deploy services one by one
for service in "${SERVICES[@]}"; do
    echo "Deploying $service..."

    # Build new image
    docker-compose build "$service"

    # Scale up with new version
    docker-compose up -d --no-deps --scale "$service"=2 "$service"

    # Wait for health check
    sleep 30

    # Check if new instance is healthy
    if docker-compose ps "$service" | grep -q "Up (healthy)"; then
        echo "$service deployed successfully"

        # Scale down old instance
        docker-compose up -d --no-deps --scale "$service"=1 "$service"
    else
        echo "Deployment failed for $service, rolling back..."
        docker-compose up -d --no-deps --scale "$service"=1 "$service"
        exit 1
    fi
done

echo "Deployment completed successfully!"
```

### Blue-Green Deployment

```bash
#!/bin/bash
# blue-green-deploy.sh

CURRENT_ENV=$(docker-compose ps | grep -q "blue" && echo "blue" || echo "green")
TARGET_ENV=$([ "$CURRENT_ENV" = "blue" ] && echo "green" || echo "blue")

echo "Current environment: $CURRENT_ENV"
echo "Target environment: $TARGET_ENV"

# Deploy to target environment
docker-compose -f "docker-compose.$TARGET_ENV.yml" up -d

# Wait for services to be healthy
echo "Waiting for services to be healthy..."
sleep 60

# Run health checks
./scripts/health-check.sh "$TARGET_ENV"

if [ $? -eq 0 ]; then
    echo "Health checks passed. Switching traffic..."

    # Update load balancer configuration
    ./scripts/switch-traffic.sh "$TARGET_ENV"

    # Stop old environment
    docker-compose -f "docker-compose.$CURRENT_ENV.yml" down

    echo "Deployment completed successfully!"
else
    echo "Health checks failed. Rolling back..."
    docker-compose -f "docker-compose.$TARGET_ENV.yml" down
    exit 1
fi
```

## Security Hardening

### Security Best Practices Implementation

1. **Non-root User Execution**
   - All containers run as non-root users
   - Minimal file permissions (644 for files, 755 for directories)
   - Read-only root filesystems where possible

2. **Network Segmentation**
   - Separate frontend and backend networks
   - No direct database access from frontend services
   - Service-to-service communication over internal networks only

3. **Secret Management**
   - Use Docker secrets for sensitive data
   - Environment-specific secret files
   - Encrypted secret storage at rest

4. **Image Security**
   - Multi-stage builds to minimize attack surface
   - Regular base image updates
   - Security scanning in CI/CD pipeline

### Docker Secrets Configuration

```yaml
secrets:
  postgres_password:
    file: ./secrets/postgres_password.txt
  redis_password:
    file: ./secrets/redis_password.txt
  microsoft_client_secret:
    file: ./secrets/microsoft_client_secret.txt
  jwt_secret:
    file: ./secrets/jwt_secret.txt
  encryption_key:
    file: ./secrets/encryption_key.txt

services:
  auth-service:
    secrets:
      - postgres_password
      - redis_password
      - microsoft_client_secret
      - jwt_secret
      - encryption_key
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
      REDIS_PASSWORD_FILE: /run/secrets/redis_password
      MICROSOFT_CLIENT_SECRET_FILE: /run/secrets/microsoft_client_secret
      JWT_SECRET_FILE: /run/secrets/jwt_secret
      ENCRYPTION_KEY_FILE: /run/secrets/encryption_key
```

## Monitoring and Observability

### Comprehensive Monitoring Stack

```yaml
# Prometheus configuration
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alert_rules.yml"

scrape_configs:
  - job_name: 'itp-services'
    static_configs:
      - targets:
        - 'auth-service:8001'
        - 'graph-gateway:8002'
        - 'workflow-service:8003'
        - 'communication-hub:8004'
        - 'rag-service:8005'
        - 'notification-service:8006'
        - 'audit-service:8007'
    metrics_path: /metrics
    scrape_interval: 10s

  - job_name: 'postgres-exporter'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis-exporter'
    static_configs:
      - targets: ['redis-exporter:9121']

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
```

### Health Check Implementation

```python
# Health check endpoint for all services
from fastapi import APIRouter, HTTPException
from datetime import datetime
import psutil
import asyncio

router = APIRouter()

@router.get("/health")
async def health_check():
    checks = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": os.getenv("SERVICE_NAME", "unknown"),
        "version": os.getenv("SERVICE_VERSION", "unknown"),
        "checks": {}
    }

    # Database connectivity check
    try:
        await database.execute("SELECT 1")
        checks["checks"]["database"] = "healthy"
    except Exception as e:
        checks["checks"]["database"] = f"unhealthy: {str(e)}"
        checks["status"] = "unhealthy"

    # Redis connectivity check
    try:
        await redis_client.ping()
        checks["checks"]["redis"] = "healthy"
    except Exception as e:
        checks["checks"]["redis"] = f"unhealthy: {str(e)}"
        checks["status"] = "unhealthy"

    # System resource checks
    memory_usage = psutil.virtual_memory().percent
    cpu_usage = psutil.cpu_percent(interval=1)

    checks["checks"]["memory"] = f"{memory_usage}%"
    checks["checks"]["cpu"] = f"{cpu_usage}%"

    if memory_usage > 90 or cpu_usage > 90:
        checks["status"] = "degraded"

    # Service-specific checks
    checks["checks"].update(await service_specific_health_checks())

    if checks["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=checks)

    return checks

@router.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe endpoint"""
    # Check if service is ready to accept traffic
    dependencies_ready = await check_dependencies_ready()

    if not dependencies_ready:
        raise HTTPException(status_code=503, detail="Service not ready")

    return {"status": "ready"}

@router.get("/live")
async def liveness_check():
    """Kubernetes liveness probe endpoint"""
    # Simple check to verify the service is alive
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}
```

## Performance Optimization

### Resource Allocation Guidelines

| Service | CPU Limit | Memory Limit | CPU Request | Memory Request |
|---------|-----------|--------------|-------------|----------------|
| Auth Service | 0.5 | 512Mi | 0.1 | 128Mi |
| Graph Gateway | 1.0 | 1Gi | 0.2 | 256Mi |
| Workflow Service | 1.0 | 1Gi | 0.3 | 512Mi |
| Communication Hub | 0.5 | 512Mi | 0.2 | 256Mi |
| RAG Service | 2.0 | 4Gi | 1.0 | 2Gi |
| Teams Adapter | 0.3 | 256Mi | 0.1 | 128Mi |
| WebUI Adapter | 0.3 | 256Mi | 0.1 | 128Mi |

### Performance Tuning

```yaml
# Docker Compose resource constraints
services:
  rag-service:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
    environment:
      # Python-specific optimizations
      PYTHONUNBUFFERED: "1"
      PYTHONDONTWRITEBYTECODE: "1"
      PYTHONHASHSEED: "random"

      # ML model optimizations
      OMP_NUM_THREADS: "4"
      MKL_NUM_THREADS: "4"
      TOKENIZERS_PARALLELISM: "false"

      # Memory management
      MALLOC_ARENA_MAX: "2"
      MALLOC_MMAP_THRESHOLD_: "131072"
      MALLOC_TRIM_THRESHOLD_: "131072"
      MALLOC_TOP_PAD_: "131072"
      MALLOC_MMAP_MAX_: "65536"
```

## Migration Strategy

### Phase 1: Infrastructure Setup (Week 1-2)
1. **Database Layer Migration**
   - Set up PostgreSQL with pgvector
   - Configure Redis cluster
   - Implement Neo4j for knowledge graphs
   - Set up MinIO for object storage

2. **Network Architecture**
   - Configure Docker networks
   - Set up load balancing
   - Implement SSL/TLS certificates

### Phase 2: Core Services Migration (Week 3-4)
1. **Authentication Service Extraction**
   - Extract auth logic from MCP Server
   - Implement centralized OAuth flows
   - Set up token management service

2. **Graph Gateway Service**
   - Extract Microsoft Graph API integration
   - Implement rate limiting and caching
   - Add monitoring and alerting

### Phase 3: Business Logic Services (Week 5-6)
1. **Workflow Service**
   - Extract Planner business logic
   - Implement task management APIs
   - Add workflow orchestration

2. **Communication Hub**
   - Centralize message routing
   - Implement protocol translation
   - Add multi-channel support

### Phase 4: Specialized Services (Week 7-8)
1. **RAG Service Enhancement**
   - Optimize for containerized deployment
   - Implement model caching
   - Add document processing pipelines

2. **Notification Service**
   - Implement multi-channel notifications
   - Add email and Teams integration
   - Set up event-driven architecture

### Phase 5: Interface Layer (Week 9-10)
1. **Adapter Services**
   - Teams adapter for Bot Framework
   - WebUI adapter for OpenWebUI integration
   - REST API adapter for external integrations

2. **Frontend Integration**
   - Update OpenWebUI configuration
   - Test Teams Bot integration
   - Validate API endpoints

### Phase 6: Production Readiness (Week 11-12)
1. **Monitoring and Observability**
   - Set up Prometheus and Grafana
   - Implement distributed tracing
   - Add log aggregation

2. **Security Hardening**
   - Security scanning and compliance
   - Secret management implementation
   - Network security policies

## Conclusion

This comprehensive dockerization blueprint transforms the Intelligent Teams Planner into a production-ready microservices architecture with the following key benefits:

### Strategic Advantages
- **Scalability**: Independent scaling of services based on demand
- **Maintainability**: Clear service boundaries and responsibilities
- **Reliability**: Improved fault isolation and recovery
- **Security**: Enhanced security through network segmentation and secrets management
- **Observability**: Comprehensive monitoring and health checking

### Technical Improvements
- **Performance**: Optimized resource allocation and caching strategies
- **Deployment**: Automated rolling and blue-green deployment strategies
- **Development**: Improved developer experience with hot reloading and debugging
- **Operations**: Simplified operations with health checks and auto-healing

### Implementation Readiness
The blueprint provides:
- Complete Docker configurations for all services
- Production-ready Docker Compose orchestration
- Security hardening implementations
- Monitoring and observability setup
- Migration strategy with clear phases
- Performance optimization guidelines

This architecture positions the Intelligent Teams Planner for enterprise-scale deployment while maintaining development agility and operational excellence.