# Intelligent Teams Planner v2.0 - Port Configuration

## Port Allocation Scheme
Starting from port 7100 with increments of 5 units

## Service Port Assignments

| Service | Port | Description | Container Name | Health Check |
|---------|------|-------------|----------------|--------------|
| **Core Infrastructure** |
| PostgreSQL | 5432 | Database server | itp-postgres | `pg_isready -U itp_user` |
| Redis | 6379 | Cache and session store | itp-redis | `redis-cli ping` |
| **Application Services** |
| MCP Server | 7100 | Microsoft Graph MCP Server | itp-mcp-server | `GET /health` |
| MCPO Proxy | 7105 | OpenWebUI to MCP Protocol Translator | itp-mcpo-proxy | `GET /health` |
| Teams Bot | 7110 | Microsoft Teams Bot Framework | itp-teams-bot | `GET /health` |
| OpenWebUI | 8888 | Conversational AI Interface | itp-openwebui | `GET /` |
| **Development/Debug** |
| Dev Server | 7120 | Development server (optional) | itp-dev-server | `GET /health` |
| Monitoring | 7125 | Prometheus/metrics (optional) | itp-monitoring | `GET /metrics` |

## Internal Network Configuration

- **Network Name**: `itp-network`
- **Internal Communication**: Services communicate via container names
- **External Access**: Only specified ports exposed to host

## Environment Variables per Service

### MCP Server (Port 7100)
```bash
PORT=7100
DATABASE_URL=postgresql+asyncpg://itp_user:itp_password_2024@postgres:5432/intelligent_teams_planner
REDIS_URL=redis://redis:6379
REDIS_PASSWORD=redis_password_2024
ENCRYPTION_KEY=12345678901234567890123456789012
TESTING_MODE=true
```

### MCPO Proxy (Port 7105)
```bash
PORT=7105
MCP_SERVER_URL=http://mcp-server:7100
REDIS_URL=redis://redis:6379
REDIS_PASSWORD=redis_password_2024
```

### Teams Bot (Port 7110)
```bash
PORT=7110
BOT_ID=test-bot-id
BOT_PASSWORD=test-bot-password
OPENWEBUI_URL=http://openwebui:8888
REDIS_URL=redis://redis:6379
REDIS_PASSWORD=redis_password_2024
```

### OpenWebUI (Port 8888)
```bash
PORT=8888
OPENAI_API_BASE_URL=http://mcpo-proxy:7105/v1
OPENAI_API_KEY=dummy-key
WEBUI_SECRET_KEY=your-secret-key
```

## Docker Network Configuration

```yaml
networks:
  itp-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

## Security Notes

- All passwords and secrets should be configured via environment variables
- Internal communication happens on the Docker network
- Only necessary ports are exposed to the host
- Health checks ensure service reliability

## Testing Endpoints

After deployment, test these endpoints:

```bash
# Core Infrastructure
curl http://localhost:5432  # PostgreSQL (will fail - database port)
redis-cli -h localhost -p 6379 -a redis_password_2024 ping

# Application Services
curl http://localhost:7100/health  # MCP Server
curl http://localhost:7105/health  # MCPO Proxy
curl http://localhost:7110/health  # Teams Bot
curl http://localhost:8888         # OpenWebUI
```

## Integration Flow

```
Teams Client → Teams Bot (7110) → OpenWebUI (8888) → MCPO Proxy (7105) → MCP Server (7100) → Graph API
                      ↓                                                                    ↓
                   Redis (6379)                                                    PostgreSQL (5432)
```