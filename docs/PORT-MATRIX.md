# Port Matrix - Intelligent Teams Planner

## Current Port Allocation

### Infrastructure Services
| Service | Internal Port | External Port | Status | Description |
|---------|---------------|---------------|--------|-------------|
| **PostgreSQL** | 5432 | 5432 | ✅ Active | Vector database with pgvector |
| **Redis** | 6379 | 6379 | ✅ Active | Caching and session management |
| **Neo4j HTTP** | 7474 | 7474 | ✅ Active | Knowledge graph web interface |
| **Neo4j Bolt** | 7687 | 7687 | ✅ Active | Knowledge graph binary protocol |

### Application Services
| Service | Internal Port | External Port | Status | Description |
|---------|---------------|---------------|--------|-------------|
| **MCP Server** | 7100 | 7200 | 🚀 Deploying | Microsoft Graph API integration |
| **MCPO Proxy** | 7105 | 7205 | 🚀 Deploying | Protocol translation layer |
| **Teams Bot** | 7110 | 7210 | 🚀 Deploying | Microsoft Teams client |
| **RAG Service** | 7120 | 7220 | 🚀 Deploying | Document intelligence & search |

### External Services
| Service | Internal Port | External Port | Status | Description |
|---------|---------------|---------------|--------|-------------|
| **OpenWebUI** | 8080 | 7115 | ✅ Active | Conversational interface (standalone) |

### Development/Debug Ports (Optional)
| Service | Internal Port | External Port | Status | Description |
|---------|---------------|---------------|--------|-------------|
| **MCP Debug** | 5678 | 5678 | 🔧 Dev Only | Python debugger |
| **MCPO Debug** | 5679 | 5679 | 🔧 Dev Only | Python debugger |
| **Teams Debug** | 5680 | 5680 | 🔧 Dev Only | Python debugger |
| **RAG Debug** | 5681 | 5681 | 🔧 Dev Only | Python debugger |

### Monitoring Services (Optional)
| Service | Internal Port | External Port | Status | Description |
|---------|---------------|---------------|--------|-------------|
| **Grafana** | 3000 | 3001 | 📊 Optional | Metrics visualization |
| **Prometheus** | 9090 | 9090 | 📊 Optional | Metrics collection |
| **Loki** | 3100 | 3100 | 📊 Optional | Log aggregation |
| **AlertManager** | 9093 | 9093 | 📊 Optional | Alert handling |

## Port Ranges

### Reserved Ranges
- **5000-5999**: Development and debugging
- **6000-6999**: Infrastructure databases
- **7000-7199**: Internal application services
- **7200-7299**: External application service access
- **7400-7499**: Graph databases and knowledge services
- **8000-8999**: Web interfaces and proxies
- **9000-9999**: Monitoring and observability

### Available Ranges
- **7300-7399**: Future application services
- **7500-7599**: Additional infrastructure
- **8100-8199**: Additional web services

## Network Configuration

### Docker Networks
- **itp-network**: `172.24.0.0/16` (Complete application)
- **itp-simple-network**: `172.23.0.0/16` (Infrastructure only)
- **itp-dev-network**: `172.21.0.0/16` (Development)
- **itp-uv-network**: `172.22.0.0/16` (UV optimized)

### External Access URLs
- **OpenWebUI**: http://localhost:7115
- **Neo4j Browser**: http://localhost:7474
- **MCP Server**: http://localhost:7200
- **MCPO Proxy**: http://localhost:7205
- **Teams Bot**: http://localhost:7210
- **RAG Service**: http://localhost:7220

## Service Dependencies

### Startup Order
1. **Infrastructure Layer**: PostgreSQL → Redis → Neo4j
2. **Core Services**: MCP Server
3. **Integration Layer**: MCPO Proxy → RAG Service
4. **Interface Layer**: Teams Bot
5. **External**: OpenWebUI (standalone)

### Health Check Endpoints
- **MCP Server**: http://localhost:7200/health
- **MCPO Proxy**: http://localhost:7205/health
- **Teams Bot**: http://localhost:7210/health
- **RAG Service**: http://localhost:7220/health

### Inter-Service Communication
- Teams Bot → OpenWebUI (external): http://host.docker.internal:7115
- MCPO Proxy → MCP Server: http://mcp-server:7100
- Services → PostgreSQL: postgres:5432
- Services → Redis: redis:6379
- Services → Neo4j: neo4j:7474, neo4j:7687

## Deployment Commands

### Infrastructure Only
```bash
./scripts/deployment/deploy-infrastructure.sh
# Ports: 5432, 6379, 7474, 7687
```

### Complete Application
```bash
docker compose -f docker-compose.complete.yml up -d
# Ports: 5432, 6379, 7474, 7687, 7200, 7205, 7210, 7220
```

### Standalone OpenWebUI
```bash
./scripts/deployment/start-openwebui.sh
# Port: 7115
```

### Development Environment
```bash
docker compose -f docker-compose.dev.yml up
# Additional debug ports: 5678-5681
```

## Troubleshooting

### Port Conflicts
If port conflicts occur:
1. Check current usage: `netstat -an | grep LISTEN`
2. Update docker-compose port mappings
3. Update service configurations
4. Restart affected services

### Service Communication
- Internal services use service names (e.g., `mcp-server:7100`)
- External access uses localhost with mapped ports
- Cross-container communication via Docker network

---

*Last Updated: October 11, 2025*
*Configuration: Complete Application Deployment*