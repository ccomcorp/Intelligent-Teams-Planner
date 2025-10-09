# RAG Service - Hybrid Multi-Source Document Intelligence

**Version:** 1.0.0  
**Port:** 7120  
**Status:** 🟡 In Development

---

## Overview

The RAG (Retrieval-Augmented Generation) Service is a hybrid document intelligence system that supports multiple document sources and provides semantic search capabilities across all uploaded documents.

### Key Features

- ✅ **Multi-Source Document Ingestion**
  - OpenWebUI Workspace/Knowledge uploads
  - Microsoft Teams chat attachments
  - Microsoft Planner task attachments
  - SharePoint/OneDrive (future)

- ✅ **Advanced Document Processing**
  - PDF, Word, PowerPoint, Text support
  - OCR for scanned documents
  - Intelligent chunking and embedding
  - Metadata extraction and enrichment

- ✅ **Semantic Search**
  - Vector similarity search using pgvector
  - Cross-source querying
  - Source attribution in results
  - Filtering by source, task, user

- ✅ **RAG Capabilities**
  - Context-aware query processing
  - Relevant document retrieval
  - Integration with LLM for responses

---

## Architecture

```
Document Sources → Ingestion Layer → Processing Layer → Storage Layer → Query Layer
                                                              ↓
                                                      PostgreSQL + pgvector
```

### Components

1. **Ingestion Layer** (`src/ingestion/`)
   - `base_handler.py` - Abstract base class
   - `openwebui_handler.py` - OpenWebUI integration
   - `teams_handler.py` - Teams chat integration
   - `planner_handler.py` - Planner task integration

2. **Processing Layer** (`src/processing/`)
   - `document_processor.py` - Multi-format processing
   - `chunker.py` - Text chunking
   - `embeddings.py` - Vector embedding generation

3. **Storage Layer** (`src/storage/`)
   - `vector_store.py` - pgvector operations
   - `metadata_store.py` - Document metadata

4. **Query Layer** (`src/query/`)
   - `semantic_search.py` - Vector similarity search
   - `rag_engine.py` - RAG query processing

---

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL with pgvector extension
- Redis (for caching)
- uv package manager

### Installation

```bash
# Navigate to service directory
cd rag-service

# Create virtual environment
uv venv --python 3.11
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Edit .env with your configuration
nano .env
```

### Database Setup

```bash
# Connect to PostgreSQL
psql -U itp_user -d intelligent_teams_planner

# Create tables (SQL provided in IMPLEMENTATION-PLAN.md)
```

### Running the Service

```bash
# Development mode
uvicorn src.main:app --reload --port 7120

# Production mode
uvicorn src.main:app --host 0.0.0.0 --port 7120 --workers 4
```

---

## API Usage

### Upload Document

```bash
curl -X POST http://localhost:7120/api/upload \
  -F "file=@document.pdf" \
  -F "source=openwebui" \
  -F "user_id=user@example.com"
```

### Query Documents

```bash
curl -X POST http://localhost:7120/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the project milestones?",
    "top_k": 5
  }'
```

### Query with Filters

```bash
curl -X POST http://localhost:7120/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the requirements?",
    "top_k": 5,
    "filters": {
      "source": "planner",
      "task_id": "task-123"
    }
  }'
```

### Health Check

```bash
curl http://localhost:7120/health
```

---

## Integration Guides

### OpenWebUI Integration

Configure OpenWebUI to use this service as the knowledge backend:

```yaml
# OpenWebUI configuration
knowledge:
  enabled: true
  backend_url: "http://rag-service:7120"
  upload_endpoint: "/api/upload"
  query_endpoint: "/api/query"
```

### Teams Bot Integration

The teams-bot service automatically forwards attachments:

```python
# teams-bot handles this automatically
# No configuration needed - just attach files in Teams chat
```

### Planner Integration

The service automatically monitors Planner tasks for attachments:

```bash
# Enable in .env
PLANNER_ENABLED=true
MICROSOFT_CLIENT_ID=your-client-id
MICROSOFT_CLIENT_SECRET=your-client-secret
MICROSOFT_TENANT_ID=your-tenant-id
```

---

## Configuration

### Environment Variables

See `.env.example` for all configuration options.

**Key Settings:**

```bash
# Service
PORT=7120
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db

# Document Processing
MAX_FILE_SIZE_MB=100
CHUNK_SIZE=1000
CHUNK_OVERLAP=200

# Embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Sources
OPENWEBUI_ENABLED=true
TEAMS_ENABLED=true
PLANNER_ENABLED=true
```

---

## Development

### Project Structure

```
rag-service/
├── src/
│   ├── ingestion/          # Document source handlers
│   ├── processing/         # Document processing
│   ├── storage/            # Database operations
│   ├── query/              # Search and RAG
│   ├── monitoring/         # Health and metrics
│   └── main.py             # FastAPI application
├── tests/                  # Test suite
├── config/                 # Configuration files
├── requirements.txt        # Dependencies
├── Dockerfile              # Container definition
└── README.md               # This file
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_document_processor.py
```

---

## Deployment

### Docker

```bash
# Build image
docker build -t rag-service:latest .

# Run container
docker run -d \
  --name rag-service \
  -p 7120:7120 \
  --env-file .env \
  rag-service:latest
```

### Docker Compose

```yaml
# Add to docker-compose.yml
rag-service:
  build: ./rag-service
  ports:
    - "7120:7120"
  environment:
    - DATABASE_URL=${DATABASE_URL}
    - REDIS_URL=${REDIS_URL}
  depends_on:
    - postgres
    - redis
```

---

## Roadmap

### Phase 1: Core Features (Week 1) ✅
- [x] Service structure
- [x] Base handler abstract class
- [ ] Document processing pipeline
- [ ] OpenWebUI integration

### Phase 2: Teams Integration (Week 2)
- [ ] Teams attachment handling
- [ ] Planner monitoring
- [ ] Unified query interface

### Phase 3: Advanced Features (Future)
- [ ] SharePoint integration
- [ ] Advanced OCR
- [ ] Multi-language support
- [ ] Document versioning

---

## Support

For issues and questions:
- Check `IMPLEMENTATION-PLAN.md` for detailed architecture
- Review `PROJECT-STATUS-REPORT.md` for project context
- See `DEVELOPMENT-ROADMAP.md` for timeline

---

**Status:** 🟡 In Development - Phase 1 Complete  
**Next:** Implement Document Processing Pipeline  
**Timeline:** 2 weeks to MVP

