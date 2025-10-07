# Intelligent Microsoft Teams Planner Management System

A conversational AI assistant for managing Microsoft Planner tasks through natural language commands within Teams environment.

## Overview

This system provides a seamless integration between Microsoft Teams and Planner, enabling users to:
- Create, read, update, and delete Planner tasks using natural language
- Generate automated reports from Planner data
- Query project information from uploaded documents
- Maintain project relationships through graph-based knowledge management

## Architecture

The system follows a microservices architecture with the following components:

- **planner-mcp-server**: Microsoft Graph API integration service
- **mcpo-proxy**: MCP to OpenAPI protocol translation
- **rag-service**: Document processing and retrieval using RAG
- **graphiti-service**: Graph-based knowledge management with Neo4j
- **doc-generator**: Automated document generation (PDF, Word, PowerPoint)
- **web-crawler**: Web content ingestion using Crawl4ai

## Technology Stack

- **Backend**: Python 3.11+ with FastAPI
- **Databases**: PostgreSQL, Redis, Qdrant, Neo4j
- **AI/ML**: LangChain, OpenWebUI, Docling
- **Document Processing**: WeasyPrint, python-docx, python-pptx
- **Web Crawling**: Crawl4ai
- **Containerization**: Docker with Docker Compose

## Prerequisites

- Docker and Docker Compose
- Microsoft 365 account with Planner access
- Azure AD app registration for Graph API access
- OpenWebUI running (existing requirement)

## Quick Start

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Intelligent-Teams-Planner
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your Microsoft Graph API credentials
   ```

3. **Start the services**
   ```bash
   docker compose up -d
   ```

4. **Verify services are running**
   ```bash
   docker compose ps
   ```

## Service Endpoints

- **Planner MCP Server**: http://localhost:8000
- **MCPO Proxy**: http://localhost:8001
- **RAG Service**: http://localhost:8002
- **Graphiti Service**: http://localhost:8003
- **Document Generator**: http://localhost:8004
- **Web Crawler**: http://localhost:8005

## Database Access

- **PostgreSQL**: localhost:5432 (user: planner, password: planner123)
- **Redis**: localhost:6379
- **Qdrant**: localhost:6333
- **Neo4j**: localhost:7474 (user: neo4j, password: planner123)

## Microsoft Graph API Setup

1. Register your application in Azure Portal
2. Configure required permissions: `Tasks.ReadWrite`
3. Add redirect URI for OAuth flow
4. Copy Client ID, Client Secret, and Tenant ID to `.env` file

## Usage Examples

Once integrated with OpenWebUI, you can use natural language commands:

- "Create a task to review the quarterly budget in the Finance plan"
- "Show me all my overdue tasks"
- "Generate a PDF report of completed tasks this week"
- "What are the key deliverables from the project documentation?"

## Development

### Running Individual Services

Each service can be run independently for development:

```bash
# Run planner MCP server
cd planner-mcp-server
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000

# Similar pattern for other services
```

### Testing

Run tests for all services:

```bash
# Run all tests
docker compose exec planner-mcp-server pytest
docker compose exec mcpo-proxy pytest
docker compose exec rag-service pytest
# etc.
```

## Monitoring

- **Health Checks**: All services expose `/health` endpoints
- **Logs**: Centralized in `./logs` directory
- **Metrics**: Service-specific metrics available via health endpoints

## Security

- OAuth 2.0 authentication with Microsoft Graph API
- Encrypted token storage
- Network isolation between services
- Environment variable-based configuration

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

[License information to be added]

## Support

For issues and questions:
- Check the documentation in `docs/`
- Review service logs in `./logs`
- Open an issue on GitHub