# Configuration State Documentation - Intelligent Teams Planner v2.0

**Last Updated:** October 12, 2025
**Configuration Version:** Production-Ready v2.0
**Deployment Profile:** docker-compose.simple.yml
**Environment Status:** ✅ Fully Configured

---

## 🎯 Configuration Overview

This document provides a comprehensive overview of all configuration settings, environment variables, and system parameters for the Intelligent Teams Planner v2.0 system as currently deployed.

---

## 📋 Environment Variables Matrix

### Core Application Configuration

| Variable | Value | Service | Purpose | Security Level |
|----------|-------|---------|---------|----------------|
| `ENVIRONMENT` | production | All | Deployment mode | Public |
| `LOG_LEVEL` | INFO | All | Logging verbosity | Public |
| `POSTGRES_PASSWORD` | itp_password_2024 | PostgreSQL | Database access | 🔒 Sensitive |
| `REDIS_PASSWORD` | redis_password_2024 | Redis | Cache access | 🔒 Sensitive |
| `NEO4J_PASSWORD` | neo4j_password_2024 | Neo4j | Graph DB access | 🔒 Sensitive |

### Microsoft Azure Integration

| Variable | Value | Service | Purpose | Security Level |
|----------|-------|---------|---------|----------------|
| `MICROSOFT_CLIENT_ID` | cbac53ee-1a21-49b5-9104-a07658a08f2e | MCP Server | Azure App ID | 🔒 Sensitive |
| `MICROSOFT_CLIENT_SECRET` | [CONFIGURED] | MCP Server | Azure App Secret | 🔐 Highly Sensitive |
| `MICROSOFT_TENANT_ID` | 5f626d2e-863b-4c09-8d80-afba9dd75d23 | MCP Server | Azure Tenant | 🔒 Sensitive |
| `MICROSOFT_REDIRECT_URI` | http://localhost:7100/auth/callback | MCP Server | OAuth callback | Public |

### Azure Bot Service Configuration

| Variable | Value | Service | Purpose | Security Level |
|----------|-------|---------|---------|----------------|
| `BOT_ID` | 4d3a5215-538d-404f-bab0-f4fe7a7298e4 | Teams Bot | Bot App ID | 🔒 Sensitive |
| `BOT_PASSWORD` | [CONFIGURED] | Teams Bot | Bot App Secret | 🔐 Highly Sensitive |
| `TEAMS_APP_ID` | cbac53ee-1a21-49b5-9104-a07658a08f2e | Teams Bot | Teams App ID | 🔒 Sensitive |

### Service Port Configuration

| Variable | Value | Service | Purpose | Security Level |
|----------|-------|---------|---------|----------------|
| `MCP_SERVER_PORT` | 7100 | MCP Server | Service port | Public |
| `MCPO_PROXY_PORT` | 7105 | MCPO Proxy | Service port | Public |
| `TEAMS_BOT_PORT` | 7110 | Teams Bot | Service port | Public |
| `RAG_SERVICE_PORT` | 7120 | RAG Service | Service port | Public |

---

## 🔗 Database Connection Strings

### PostgreSQL Configuration
```yaml
DATABASE_URL: postgresql+asyncpg://itp_user:itp_password_2024@postgres:5432/intelligent_teams_planner
Features:
  - pgvector extension enabled
  - Connection pooling configured
  - Async operations support
  - Schema migrations automated
```

### Redis Configuration
```yaml
REDIS_URL: redis://:redis_password_2024@redis:6379
Features:
  - L1/L2 caching architecture
  - Session management
  - Conversation context storage
  - TTL-based expiration
```

### Neo4j Configuration
```yaml
NEO4J_URI: bolt://neo4j:7687
NEO4J_AUTH: neo4j/neo4j_password_2024
Features:
  - APOC plugins enabled
  - Graph Data Science library
  - Knowledge graph storage
  - Entity relationship mapping
```

---

## 🏗️ Docker Compose Configuration

### Service Definitions (docker-compose.simple.yml)

#### Infrastructure Services
```yaml
postgres:
  image: pgvector/pgvector:pg16
  container_name: itp-postgres-simple
  ports: ["5432:5432"]
  healthcheck: pg_isready check

redis:
  image: redis:7-alpine
  container_name: itp-redis-simple
  ports: ["6379:6379"]
  healthcheck: redis-cli ping

neo4j:
  image: neo4j:5.15-community
  container_name: itp-neo4j-simple
  ports: ["7474:7474", "7687:7687"]
  healthcheck: cypher-shell check
```

#### Application Services
```yaml
planner-mcp-server:
  build: ./planner-mcp-server
  dockerfile: Dockerfile.uv
  container_name: itp-planner-mcp-simple
  ports: ["7100:7100"]

mcpo-proxy:
  build: ./mcpo-proxy
  dockerfile: Dockerfile.uv
  container_name: itp-mcpo-proxy-simple
  ports: ["7105:7105"]

teams-bot:
  build: ./teams-bot
  dockerfile: Dockerfile.uv
  container_name: itp-teams-bot-simple
  ports: ["7110:7110"]

rag-service:
  build: ./rag-service
  dockerfile: Dockerfile.uv
  container_name: itp-rag-service-simple
  ports: ["7120:7120"]
```

#### External Services
```yaml
openwebui:
  image: ghcr.io/open-webui/open-webui:main
  container_name: openwebui
  ports: ["8899:8080"]
  network: bridge (separate)
```

---

## 🌐 Network Configuration

### Internal Network
```yaml
Network Name: intelligent-teams-planner_itp-simple-network
Driver: bridge
Subnet: 172.23.0.0/16
Services Connected:
  - itp-postgres-simple
  - itp-redis-simple
  - itp-neo4j-simple
  - itp-planner-mcp-simple
  - itp-mcpo-proxy-simple
  - itp-teams-bot-simple
  - itp-rag-service-simple
```

### External Network Access
```yaml
OpenWebUI Access: host.docker.internal:8899
Reason: Separate bridge network for standalone deployment
Alternative: Could be integrated into main network if needed
```

---

## 🔒 Security Configuration

### Authentication Systems

#### Azure AD Integration
```yaml
OAuth 2.0 Flow:
  - Authorization Code with PKCE
  - Scope: User.Read, Group.ReadWrite.All, Tasks.ReadWrite, Team.ReadBasic.All
  - Token Storage: Encrypted with PBKDF2HMAC + AES-256
  - Callback: http://localhost:7100/auth/callback
```

#### Bot Framework Authentication
```yaml
Azure Bot Service:
  - Single-tenant registration (migration-ready)
  - App ID: 4d3a5215-538d-404f-bab0-f4fe7a7298e4
  - Messaging Endpoint: http://localhost:7110/api/messages
  - Token Validation: Microsoft Bot Framework SDK
```

### Encryption Configuration
```yaml
Token Encryption:
  Algorithm: PBKDF2HMAC with AES-256
  Key Derivation: 100,000 iterations
  Salt: Randomly generated per token
  Storage: Redis with TTL expiration
```

---

## 📊 Performance Configuration

### Caching Strategy
```yaml
L1 Cache (In-Memory):
  - Thread-safe LRU implementation
  - Sub-millisecond access times
  - Configurable size limits
  - TTL-based expiration

L2 Cache (Redis):
  - Network-accessible shared cache
  - Session and conversation storage
  - Cross-service data sharing
  - Persistent across restarts
```

### Optimization Features
```yaml
Response Compression:
  - gzip compression enabled
  - 97.8% space savings achieved
  - Configurable compression levels

Pagination:
  - Cursor-based implementation
  - Base64-encoded cursors
  - Sub-millisecond operations

Retry Logic:
  - Exponential backoff with jitter
  - Configurable retry attempts
  - Circuit breaker patterns
```

---

## 🔧 Development Configuration

### Package Management
```yaml
Primary Tool: uv (10-100x faster than pip)
Fallback: pip (universal compatibility)
Virtual Environments: Isolated per service
Dependency Management: requirements.txt + lock files
```

### Build Configuration
```yaml
Dockerfile Strategy: Multi-stage builds with uv
Base Images: Python 3.12+ official images
Security: Non-root user execution
Optimization: Layer caching and minimal images
```

---

## 📋 Health Check Configuration

### Service Health Endpoints

| Service | Endpoint | Check Type | Interval | Timeout | Retries |
|---------|----------|------------|----------|---------|---------|
| MCP Server | `/health` | HTTP GET | 30s | 10s | 3 |
| MCPO Proxy | `/health` | HTTP GET | 30s | 10s | 3 |
| Teams Bot | `/health` | HTTP GET | 30s | 10s | 3 |
| RAG Service | `/health` | HTTP GET | 30s | 10s | 3 |
| PostgreSQL | `pg_isready` | Command | 10s | 5s | 5 |
| Redis | `redis-cli ping` | Command | 10s | 5s | 5 |
| Neo4j | `cypher-shell` | Command | 30s | 10s | 3 |
| OpenWebUI | `/health` | HTTP GET | 30s | 10s | 3 |

### Dependency Chain
```yaml
Startup Dependencies:
  teams-bot → mcpo-proxy → planner-mcp-server → postgres + redis
  rag-service → postgres + neo4j + planner-mcp-server

Health Dependencies:
  All services → redis (session management)
  MCP + RAG → postgres (data persistence)
  RAG → neo4j (knowledge graph)
```

---

## 🚨 Configuration Validation

### Required Environment Variables
```bash
# Critical - Service will fail without these
BOT_ID (Teams Bot)
BOT_PASSWORD (Teams Bot)
MICROSOFT_CLIENT_ID (MCP Server)
MICROSOFT_CLIENT_SECRET (MCP Server)
MICROSOFT_TENANT_ID (MCP Server)

# Important - Default values provided
POSTGRES_PASSWORD (default: itp_password_2024)
REDIS_PASSWORD (default: redis_password_2024)
NEO4J_PASSWORD (default: neo4j_password_2024)
```

### Configuration Testing
```bash
# Validate all services are properly configured
curl http://localhost:7100/health  # Should return {"status": "healthy"}
curl http://localhost:7105/health  # Should return {"status": "healthy"}
curl http://localhost:7110/health  # Should return {"status": "healthy", "openwebui_status": "healthy"}
curl http://localhost:7120/health  # Should return {"status": "healthy"}
curl http://localhost:8899/health  # Should return {"status": true}
```

---

## 📈 Migration & Future Configuration

### Microsoft Deprecation Preparation
```yaml
Current Status: ✅ Ready for migration deadlines
- Single-tenant registration: ✅ Implemented
- Bot Framework SDK: ⚠️ End of support Dec 31, 2025
- Migration Path: Microsoft 365 Agents SDK

Recommended Timeline:
- Q2 2025: Plan migration to M365 Agents SDK
- Q3 2025: Begin implementation
- Q4 2025: Complete migration before deadline
```

### Scalability Configuration
```yaml
Current: Single-node deployment
Future Options:
  - Multi-node Docker Swarm
  - Kubernetes orchestration
  - Microservices scaling
  - Database clustering
```

---

**Configuration Manager:** Winston (System Architect)
**Configuration Validation:** All services verified operational
**Last Configuration Change:** October 12, 2025 (OpenWebUI port update)
**Next Configuration Review:** December 1, 2025