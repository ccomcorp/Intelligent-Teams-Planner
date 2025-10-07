import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
import httpx

structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True
)

logger = structlog.get_logger(__name__)

app = FastAPI(title="RAG Service", description="Document processing and retrieval service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global services
qdrant_client: QdrantClient = None
embedding_model: SentenceTransformer = None

class DocumentUploadResponse(BaseModel):
    success: bool
    message: str
    document_id: Optional[str] = None
    chunks_processed: Optional[int] = None

class QueryRequest(BaseModel):
    query: str
    collection_name: str = "documents"
    limit: int = 5
    threshold: float = 0.7

class QueryResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]]
    query: str

@app.on_event("startup")
async def startup_event():
    global qdrant_client, embedding_model

    try:
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        qdrant_client = QdrantClient(url=qdrant_url)

        # Initialize embedding model
        model_name = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        embedding_model = SentenceTransformer(model_name)

        # Create default collection
        await ensure_collection_exists("documents")

        logger.info("RAG Service started successfully")

    except Exception as e:
        logger.error("Failed to initialize RAG service", error=str(e))
        raise

async def ensure_collection_exists(collection_name: str):
    """Ensure Qdrant collection exists"""
    try:
        collections = qdrant_client.get_collections().collections
        collection_names = [col.name for col in collections]

        if collection_name not in collection_names:
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE)
            )
            logger.info("Created Qdrant collection", collection_name=collection_name)

    except Exception as e:
        logger.error("Error managing Qdrant collection", error=str(e))
        raise

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Simple text chunking strategy"""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Try to break at sentence boundary
        if end < len(text):
            last_period = chunk.rfind('.')
            if last_period > chunk_size * 0.7:
                chunk = chunk[:last_period + 1]
                end = start + last_period + 1

        chunks.append(chunk.strip())
        start = end - overlap

        if start >= len(text):
            break

    return chunks

def extract_text_from_file(file_content: bytes, filename: str) -> str:
    """Extract text from uploaded file"""
    try:
        if filename.lower().endswith('.txt'):
            return file_content.decode('utf-8')
        elif filename.lower().endswith('.pdf'):
            # Basic PDF text extraction
            import pypdf
            import io

            pdf_reader = pypdf.PdfReader(io.BytesIO(file_content))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text
        elif filename.lower().endswith('.docx'):
            # Basic DOCX text extraction
            from docx import Document
            import io

            doc = Document(io.BytesIO(file_content))
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        else:
            # Try to decode as text
            return file_content.decode('utf-8', errors='ignore')

    except Exception as e:
        logger.error("Error extracting text from file", filename=filename, error=str(e))
        raise HTTPException(status_code=400, detail=f"Failed to extract text from {filename}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check Qdrant connection
        collections = qdrant_client.get_collections()
        qdrant_status = "healthy"
    except Exception as e:
        qdrant_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if qdrant_status == "healthy" else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "qdrant_status": qdrant_status,
        "embedding_model": embedding_model.get_sentence_embedding_dimension() if embedding_model else "not loaded"
    }

@app.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    collection_name: str = Form("documents"),
    metadata: str = Form("{}")
):
    """Upload and process a document"""
    try:
        # Read file content
        file_content = await file.read()

        # Extract text
        text = extract_text_from_file(file_content, file.filename)

        if not text.strip():
            raise HTTPException(status_code=400, detail="No text content found in file")

        # Chunk the text
        chunks = chunk_text(text)

        # Generate embeddings
        embeddings = embedding_model.encode(chunks)

        # Ensure collection exists
        await ensure_collection_exists(collection_name)

        # Store in Qdrant
        points = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            point_id = f"{file.filename}_{i}_{int(datetime.utcnow().timestamp())}"

            import json
            metadata_dict = json.loads(metadata) if metadata != "{}" else {}

            point = PointStruct(
                id=point_id,
                vector=embedding.tolist(),
                payload={
                    "text": chunk,
                    "filename": file.filename,
                    "chunk_index": i,
                    "upload_time": datetime.utcnow().isoformat(),
                    **metadata_dict
                }
            )
            points.append(point)

        qdrant_client.upsert(collection_name=collection_name, points=points)

        logger.info("Document processed successfully",
                   filename=file.filename,
                   chunks=len(chunks),
                   collection=collection_name)

        return DocumentUploadResponse(
            success=True,
            message=f"Document '{file.filename}' processed successfully",
            document_id=file.filename,
            chunks_processed=len(chunks)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing document", filename=file.filename, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")

@app.post("/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest):
    """Query documents using semantic search"""
    try:
        # Generate query embedding
        query_embedding = embedding_model.encode([request.query])[0]

        # Search in Qdrant
        search_results = qdrant_client.search(
            collection_name=request.collection_name,
            query_vector=query_embedding.tolist(),
            limit=request.limit,
            score_threshold=request.threshold
        )

        # Format results
        results = []
        for result in search_results:
            results.append({
                "text": result.payload["text"],
                "filename": result.payload.get("filename", "unknown"),
                "score": result.score,
                "metadata": {k: v for k, v in result.payload.items()
                           if k not in ["text", "filename"]}
            })

        logger.info("Query executed",
                   query=request.query[:50] + "...",
                   results_count=len(results),
                   collection=request.collection_name)

        return QueryResponse(
            success=True,
            results=results,
            query=request.query
        )

    except Exception as e:
        logger.error("Error querying documents", query=request.query, error=str(e))
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@app.get("/collections")
async def list_collections():
    """List all available collections"""
    try:
        collections = qdrant_client.get_collections()
        return {
            "collections": [
                {
                    "name": col.name,
                    "vectors_count": qdrant_client.count(col.name).count
                }
                for col in collections.collections
            ]
        }
    except Exception as e:
        logger.error("Error listing collections", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list collections")

@app.delete("/collections/{collection_name}")
async def delete_collection(collection_name: str):
    """Delete a collection"""
    try:
        qdrant_client.delete_collection(collection_name)
        return {"success": True, "message": f"Collection '{collection_name}' deleted"}
    except Exception as e:
        logger.error("Error deleting collection", collection=collection_name, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to delete collection")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)