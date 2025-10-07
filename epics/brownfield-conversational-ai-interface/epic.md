# Epic 1: Brownfield Conversational AI Interface Enhancement

## Status
Draft

## Epic Overview

**As a** Teams user,
**I want** a seamless conversational AI interface integrated with my existing Microsoft Planner workflow,
**so that** I can manage tasks naturally without leaving the Teams environment.

## Epic Goal

Enhance the existing Intelligent Teams Planner v2.0 architecture by adding OpenWebUI as a conversational interface hub that integrates with the current Microsoft Teams Planner infrastructure. This is a brownfield enhancement that adds conversational capabilities to the existing Docker-orchestrated microservices architecture without replacing the core Microsoft Graph API integration or Teams Bot functionality.

## Integration Requirements

This epic focuses on interface enhancement rather than architectural replacement:

- **Preserve Existing Architecture**: All current microservices (Teams Bot, MCP Server, PostgreSQL, Redis) remain intact
- **Add Conversational Layer**: OpenWebUI becomes the central conversational hub
- **Enhance Teams Integration**: Teams Bot forwards messages to OpenWebUI instead of direct processing
- **Protocol Translation**: MCPO Proxy enables OpenWebUI to communicate with existing MCP Server
- **Natural Language Processing**: Users can interact with Planner through conversational commands

## Architecture Enhancement

```
BEFORE: Teams Client → Teams Bot → MCP Server → Graph API
AFTER:  Teams Client → Teams Bot → OpenWebUI → MCPO Proxy → MCP Server → Graph API
```

### New Components Added:
- **OpenWebUI (Port 3000)**: Conversational AI interface with RAG capabilities
- **MCPO Proxy (Port 8001)**: Protocol translation between OpenWebUI and MCP Server

### Enhanced Components:
- **Teams Bot (Port 3978)**: Modified to forward messages to OpenWebUI
- **MCP Server (Port 8000)**: Enhanced with additional tools for natural language processing
- **PostgreSQL + Redis**: Extended schemas for conversation context and embeddings

## Acceptance Criteria

1. **Teams Bot Integration**: Teams Bot successfully forwards user messages to OpenWebUI and returns conversational responses
2. **Protocol Translation**: MCPO Proxy translates OpenWebUI requests to MCP format and vice versa
3. **Natural Language Commands**: Users can create, read, update, and delete Planner tasks using natural language
4. **Conversation Context**: System maintains context across multiple user interactions
5. **Existing Functionality Preserved**: All current Microsoft Graph API operations continue working
6. **Performance Maintained**: Response times remain under 3 seconds for simple queries
7. **Error Handling**: Graceful fallback when conversational interface is unavailable

## Integration Verification

### IV1: Existing Microsoft Graph API Integration Preserved
- All current Planner operations (CRUD) continue functioning
- Authentication flow remains unchanged
- Rate limiting and caching mechanisms intact

### IV2: Teams Bot Compatibility Maintained
- Bot registration and Teams app manifest remain valid
- Message handling preserves Teams-specific features
- Error handling maintains Teams bot compliance

### IV3: Database Schema Compatibility
- Existing PostgreSQL tables and relationships preserved
- New tables added for conversation context without conflicts
- Redis caching patterns remain functional

## Stories

### Story 1.1: Teams Bot Message Forwarding
**As a** Teams user,
**I want** my Teams messages forwarded to OpenWebUI,
**so that** I can interact with the AI conversational interface through Teams.

**Acceptance Criteria:**
1. Teams Bot receives messages from Teams client
2. Messages are forwarded to OpenWebUI API endpoint
3. OpenWebUI responses are returned to Teams user
4. Message formatting preserved during forwarding
5. Error handling when OpenWebUI is unavailable
6. Authentication context passed through forwarding chain

### Story 1.2: MCPO Proxy Protocol Translation
**As a** system integrator,
**I want** OpenWebUI to communicate with the existing MCP Server,
**so that** conversational commands can trigger Planner operations.

**Acceptance Criteria:**
1. MCPO Proxy translates OpenWebUI tool calls to MCP format
2. MCP Server responses translated back to OpenWebUI format
3. Error messages properly propagated through translation layers
4. Real-time communication via WebSocket supported
5. Auto-discovery of MCP Server capabilities
6. Request/response logging for debugging

### Story 1.3: Natural Language Command Processing
**As a** Teams user,
**I want** to manage Planner tasks using natural language,
**so that** I can work more efficiently without learning specific commands.

**Acceptance Criteria:**
1. Intent recognition for create, read, update, delete operations
2. Entity extraction for task titles, due dates, assignees
3. Context-aware parameter resolution
4. Disambiguation when commands are unclear
5. Support for relative date expressions
6. Batch operation support for multiple tasks

## Technical Constraints

### Existing Technology Stack (Preserved)
- **Backend**: Python 3.11+ with FastAPI
- **Database**: PostgreSQL with pgvector, Redis for caching
- **Authentication**: Microsoft Graph SDK with OAuth 2.0
- **Containerization**: Docker Compose orchestration
- **API Integration**: Microsoft Graph API v1.0

### New Technology Additions
- **OpenWebUI**: ghcr.io/open-webui/open-webui:main
- **Protocol Translation**: Custom MCPO Proxy service
- **Natural Language**: Enhanced MCP Server with NLP capabilities

### Integration Approach
- **Database**: Extend existing schema with conversation tables
- **API**: Add OpenWebUI endpoints while preserving MCP Server API
- **Frontend**: OpenWebUI becomes primary user interface
- **Testing**: Integration tests for new conversation flow

## Risk Assessment and Mitigation

### Technical Risks
- **OpenWebUI Integration Complexity**: Mitigate with thorough protocol testing
- **Performance Impact**: Monitor response times and optimize translation layer
- **Message Forwarding Failures**: Implement fallback to direct Teams Bot processing

### Integration Risks
- **MCP Protocol Compatibility**: Validate against MCP specification
- **Teams Bot Changes**: Minimal changes to preserve Teams compliance
- **Database Migration**: Non-destructive schema additions only

### Deployment Risks
- **Service Dependencies**: Health checks ensure proper startup sequence
- **Configuration Management**: Environment variables for all new settings
- **Rollback Strategy**: Docker Compose allows quick service rollback

## Development Notes

### Source Tree Integration
- **teams-bot/**: Modify message handling to forward to OpenWebUI
- **mcpo-proxy/**: New service for protocol translation
- **openwebui/**: Configuration and custom tools
- **planner-mcp-server/**: Enhanced with conversational tools
- **docker-compose.yml**: Add OpenWebUI and MCPO Proxy services

### Testing Standards
- **Unit Tests**: pytest for all new components
- **Integration Tests**: End-to-end conversation flow testing
- **Performance Tests**: Response time validation
- **File Location**: tests/ directory in each service folder

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|---------|
| 2025-10-06 | 1.0 | Initial brownfield epic creation | BMad Framework |

## Epic Dependencies

- Existing Docker Compose environment running
- Microsoft Graph API credentials configured
- Teams Bot registered and installed
- PostgreSQL and Redis services healthy