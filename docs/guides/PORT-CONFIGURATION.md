# Intelligent Teams Planner v2.0 - Port Configuration

## Current Production Deployment (October 12, 2025)

### Port Allocation Scheme
Primary services: 7100-7125 with increments of 5 units
Infrastructure: Standard ports (5432, 6379, 7474/7687)
UI Services: 8899 (OpenWebUI)

## Service Port Assignments

| Service | Port | Description | Container Name | Health Check | Status |
|---------|------|-------------|----------------|--------------|--------|
| **Core Infrastructure** |
| PostgreSQL | 5432 | Database server with pgvector | itp-postgres-simple | `pg_isready -U itp_user` | ✅ Healthy |
| Redis | 6379 | Cache and session store | itp-redis-simple | `redis-cli ping` | ✅ Healthy |
| Neo4j | 7474/7687 | Knowledge graph database | itp-neo4j-simple | `GET /db/data/` | ✅ Healthy |
| **Application Services** |
| MCP Server | 7100 | Microsoft Graph MCP Server | itp-planner-mcp-simple | `GET /health` | ✅ Healthy |
| MCPO Proxy | 7105 | OpenAI ↔ MCP Protocol Translator | itp-mcpo-proxy-simple | `GET /health` | ✅ Healthy |
| Teams Bot | 7110 | Microsoft Teams Bot Framework | itp-teams-bot-simple | `GET /health` | ✅ Healthy |
| RAG Service | 7120 | Document processing & semantic search | itp-rag-service-simple | `GET /health` | ✅ Healthy |
| **User Interface** |
| OpenWebUI | 8899 | Conversational AI Interface | openwebui | `GET /health` | ✅ Healthy |

## Network Architecture

### Internal Network Configuration
- **Network Name**: `intelligent-teams-planner_itp-simple-network`
- **Subnet**: `172.23.0.0/16`
- **Internal Communication**: Services communicate via container names
- **External Access**: Only specified ports exposed to host
- **OpenWebUI**: Runs on separate bridge network (accessible via host.docker.internal)

### Azure Bot Service Integration
- **Bot Registration**: Azure Bot Service (Single-tenant recommended)
- **OAuth Callback**: `http://localhost:7100/auth/callback` (MCP Server)
- **Teams Messaging**: `http://localhost:7110/api/messages` (Teams Bot)

## Current Environment Configuration

### MCP Server (Port 7100) - Microsoft Graph Integration
```bash
PORT=7100
DATABASE_URL=postgresql+asyncpg://itp_user:itp_password_2024@postgres:5432/intelligent_teams_planner
NEO4J_URI=bolt://neo4j:7687
REDIS_URL=redis://:redis_password_2024@redis:6379
MICROSOFT_CLIENT_ID=cbac53ee-1a21-49b5-9104-a07658a08f2e
MICROSOFT_TENANT_ID=5f626d2e-863b-4c09-8d80-afba9dd75d23
MICROSOFT_REDIRECT_URI=http://localhost:7100/auth/callback
ENCRYPTION_KEY=ITP_ENCRYPTION_KEY_2024_SECURE
```

### MCPO Proxy (Port 7105) - Protocol Translation
```bash
PORT=7105
PLANNER_MCP_URL=http://planner-mcp-server:7100
REDIS_URL=redis://:redis_password_2024@redis:6379
```

### Teams Bot (Port 7110) - Azure Bot Framework
```bash
PORT=7110
BOT_ID=4d3a5215-538d-404f-bab0-f4fe7a7298e4
BOT_PASSWORD=[YOUR_BOT_PASSWORD]
TEAMS_APP_ID=cbac53ee-1a21-49b5-9104-a07658a08f2e
OPENWEBUI_URL=http://host.docker.internal:8899
REDIS_URL=redis://:redis_password_2024@redis:6379
```

### RAG Service (Port 7120) - Document Processing
```bash
PORT=7120
DATABASE_URL=postgresql+asyncpg://itp_user:itp_password_2024@postgres:5432/intelligent_teams_planner
NEO4J_URI=bolt://neo4j:7687
REDIS_URL=redis://:redis_password_2024@redis:6379
PLANNER_MCP_URL=http://planner-mcp-server:7100
```

### OpenWebUI (Port 8899) - Conversational Interface
```bash
PORT=8080 (internal)
EXTERNAL_PORT=8899
OPENAI_API_BASE_URL=http://mcpo-proxy:7105/v1
OPENAI_API_KEY=dummy-key
```

## Docker Network Configuration

```yaml
networks:
  itp-simple-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.23.0.0/16
```

## Security Notes

- All passwords and secrets configured via environment variables
- Internal communication happens on the Docker network
- Only necessary ports are exposed to the host
- Health checks ensure service reliability
- Azure Bot Service credentials properly secured
- OAuth flow handled through dedicated MCP Server endpoint

## Production Testing Endpoints

After deployment, test these endpoints:

```bash
# Core Infrastructure Health
redis-cli -h localhost -p 6379 -a redis_password_2024 ping
curl http://localhost:7474  # Neo4j HTTP interface

# Application Services Health
curl http://localhost:7100/health  # MCP Server
curl http://localhost:7105/health  # MCPO Proxy
curl http://localhost:7110/health  # Teams Bot
curl http://localhost:7120/health  # RAG Service
curl http://localhost:8899/health  # OpenWebUI
```

## Current Integration Flow (October 12, 2025)

```
Teams Client → Teams Bot (7110) → OpenWebUI (8899) → MCPO Proxy (7105) → MCP Server (7100) → Microsoft Graph API
                      ↓                    ↑                                        ↑
                   Redis (6379)      host.docker.internal            OAuth Callback (7100/auth/callback)
                      ↓                                                             ↓
                 RAG Service (7120) ←→ PostgreSQL (5432) + Neo4j (7474/7687)
```

## Service Dependencies

### Startup Order
1. **Infrastructure**: PostgreSQL, Redis, Neo4j
2. **Core Services**: MCP Server, RAG Service
3. **Protocol Layer**: MCPO Proxy
4. **User Interface**: Teams Bot, OpenWebUI

### Health Check Dependencies
- Teams Bot → MCPO Proxy → MCP Server → PostgreSQL/Redis
- RAG Service → PostgreSQL + Neo4j + MCP Server
- All services → Redis (session/cache management)