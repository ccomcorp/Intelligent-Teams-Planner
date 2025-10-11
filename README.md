# Intelligent Teams Planner v2.0 🚀

An OpenWebUI-centric universal assistant for Microsoft Teams Planner management with natural language processing capabilities.

## Architecture Overview

```
Teams Client → Teams Bot → OpenWebUI → MCPO Proxy → MCP Server → Graph API
```

### Core Components

- **OpenWebUI**: Central conversational AI hub
- **Teams Bot**: Lightweight Microsoft Teams client
- **MCPO Proxy**: Protocol translation between OpenWebUI and MCP
- **MCP Server**: Business logic and Microsoft Graph API integration
- **PostgreSQL**: Unified database with pgvector for embeddings
- **Redis**: Caching and session management

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Microsoft Azure AD app registration
- Microsoft Teams bot registration
- OpenAI API key (for embeddings)

### 1. Clone and Setup

```bash
git clone <repository-url>
cd Intelligent-Teams-Planner
cp .env.example .env
# Edit .env with your credentials
```

### 2. Configure Microsoft Graph API

1. Register application at [Azure Portal](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps)
2. Add required permissions:
   - `Group.Read.All`
   - `Tasks.ReadWrite`
3. Generate client secret
4. Update `.env` with credentials

### 3. Configure Teams Bot

1. Register bot at [Bot Framework](https://dev.botframework.com/)
2. Create Teams app manifest
3. Install app in Teams
4. Update `.env` with bot credentials

### 4. Launch Services

```bash
# Start all services
docker compose up -d

# Check service health
./scripts/test-services.sh

# View logs
docker compose logs -f
```

### 5. Access OpenWebUI

- Open http://localhost:3000
- Configure MCPO Proxy endpoint: `http://localhost:8001`
- Start conversational Planner management

## Service Architecture

### OpenWebUI (Port 3000)
- **Purpose**: Central conversational interface
- **Features**: Chat, RAG, model management
- **Integration**: Connects to MCPO Proxy for Planner tools

### MCPO Proxy (Port 8001)
- **Purpose**: Protocol translation layer
- **Function**: Translates OpenWebUI requests to MCP format
- **API**: OpenAPI-compatible endpoints

### Planner MCP Server (Port 8000)
- **Purpose**: Core business logic
- **Features**: Graph API integration, OAuth, caching
- **Protocol**: Model Context Protocol (MCP)

### Teams Bot (Port 3978)
- **Purpose**: Microsoft Teams interface
- **Features**: Lightweight client forwarding to OpenWebUI
- **Integration**: Bot Framework SDK

### Database Services
- **PostgreSQL**: Primary data storage with pgvector
- **Redis**: Caching and session management

## Development

### Project Structure

```
├── teams-bot/           # Microsoft Teams bot client
├── planner-mcp-server/  # Core MCP server
├── mcpo-proxy/          # OpenWebUI integration proxy
├── openwebui/           # OpenWebUI configuration
├── rag-service/         # Document processing and vector search
├── database/            # Database schemas and migrations
├── epics/               # Active feature epics and stories
├── epics-archive/       # Completed or archived epics
├── docs/                # Organized documentation
│   ├── guides/          # Configuration and setup guides
│   ├── reports/         # Status and analysis reports
│   ├── implementation/  # Implementation details and conventions
│   └── status/          # Current project status files
├── scripts/             # Development and deployment scripts
│   ├── deployment/      # Deployment automation
│   ├── setup/           # Environment setup scripts
│   └── validation/      # Testing and validation scripts
├── tests/               # Test files and integration tests
├── monitoring/          # Grafana and monitoring configuration
└── archive/             # Previous implementations
```

### Local Development

```bash
# Install development dependencies
./scripts/dev/setup.sh

# Start development environment
docker compose -f docker-compose.dev.yml up

# Run tests
./scripts/test/run-all.sh

# Format and lint
./scripts/dev/format.sh
```

### Testing

```bash
# Test all services
./scripts/test-services.sh

# Test specific service
docker compose exec planner-mcp-server pytest

# Integration tests
./scripts/test/integration.sh
```

## API Documentation

### MCPO Proxy API
- **OpenAPI Spec**: http://localhost:8001/openapi.json
- **Swagger UI**: http://localhost:8001/docs

### MCP Server Tools
- **Available Tools**: http://localhost:8000/tools
- **Health Check**: http://localhost:8000/health

## Configuration

### Environment Variables

See `.env.example` for complete configuration options.

Key configurations:
- Microsoft Graph API credentials
- Teams bot registration
- OpenAI API key for embeddings
- Database and Redis passwords

### OpenWebUI Setup

1. Access http://localhost:3000
2. Navigate to Settings → Connections
3. Add OpenAI-compatible API:
   - Base URL: `http://localhost:8001/v1`
   - API Key: `dummy-key`
4. Test connection and start using Planner tools

## Troubleshooting

### Common Issues

**Service startup failures:**
```bash
# Check service logs
docker compose logs [service-name]

# Restart specific service
docker compose restart [service-name]
```

**Authentication issues:**
```bash
# Verify Microsoft Graph credentials
curl -X POST http://localhost:8000/auth/login

# Check token status
curl http://localhost:8000/auth/status
```

**OpenWebUI connection:**
```bash
# Test MCPO Proxy connectivity
curl http://localhost:8001/health

# Verify tool discovery
curl http://localhost:8001/tools
```

### Service Health Checks

```bash
# Quick health check all services
./scripts/test-services.sh

# Individual service status
curl http://localhost:3000/health    # OpenWebUI
curl http://localhost:8001/health    # MCPO Proxy
curl http://localhost:8000/health    # MCP Server
curl http://localhost:3978/api/messages  # Teams Bot
```

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/your-feature`
3. Follow coding standards in `CLAUDE.md`
4. Add tests for new functionality
5. Submit pull request

## Documentation

### Project Documentation
- [Product Requirements](docs/prd-mvp.md)
- [Architecture Documentation](docs/v2/architecture.md)

### Implementation Guides
- [Package Management Guide](docs/implementation/PACKAGE_MANAGEMENT_COMPLETE.md)
- [UV Implementation Guide](docs/implementation/UV_IMPLEMENTATION_COMPLETE.md)
- [Epic Naming Conventions](docs/implementation/EPIC-NAMING-CONVENTION-UPDATE.md)

### Configuration Guides
- [Development Roadmap](docs/guides/DEVELOPMENT-ROADMAP.md)
- [Port Configuration](docs/guides/PORT-CONFIGURATION.md)

### Status Reports
- [Project Status Summary](docs/status/PROJECT-STATUS-SUMMARY.md)
- [Latest Updates](docs/status/UPDATES-2025-01-10.md)

### Analysis Reports
- [Comprehensive Project Review](docs/reports/COMPREHENSIVE-PROJECT-REVIEW-2025-01-10.md)
- [Testing Results](docs/reports/REAL-TESTING-RESULTS.md)
- [Logical Progression Analysis](docs/reports/LOGICAL-PROGRESSION-ANALYSIS.md)

## License

MIT License - see LICENSE file for details.

## Support

- GitHub Issues: Report bugs and feature requests
- Documentation: Check `docs/` directory
- Logs: Use `docker compose logs` for debugging