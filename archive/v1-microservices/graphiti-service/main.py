import os
from datetime import datetime
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import structlog
from neo4j import GraphDatabase
import httpx

structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True
)

logger = structlog.get_logger(__name__)

app = FastAPI(title="Graphiti Service", description="Graph knowledge management service", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Global services
neo4j_driver = None

class RelationshipRequest(BaseModel):
    source_id: str
    target_id: str
    relationship_type: str
    properties: Dict[str, Any] = {}

class QueryRequest(BaseModel):
    query: str
    parameters: Dict[str, Any] = {}

@app.on_event("startup")
async def startup_event():
    global neo4j_driver

    try:
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "planner123")

        neo4j_driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

        # Test connection
        with neo4j_driver.session() as session:
            session.run("RETURN 1")

        logger.info("Graphiti Service started successfully")

    except Exception as e:
        logger.error("Failed to initialize Graphiti service", error=str(e))
        raise

@app.on_event("shutdown")
async def shutdown_event():
    if neo4j_driver:
        neo4j_driver.close()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        with neo4j_driver.session() as session:
            result = session.run("RETURN 1 as test")
            result.single()
        neo4j_status = "healthy"
    except Exception as e:
        neo4j_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if neo4j_status == "healthy" else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "neo4j_status": neo4j_status
    }

@app.post("/nodes")
async def create_node(node_data: Dict[str, Any]):
    """Create a node in the graph"""
    try:
        node_type = node_data.get("type", "Node")
        properties = {k: v for k, v in node_data.items() if k != "type"}

        with neo4j_driver.session() as session:
            query = f"CREATE (n:{node_type} $properties) RETURN n"
            result = session.run(query, properties=properties)
            node = result.single()

            return {"success": True, "node": dict(node["n"])}

    except Exception as e:
        logger.error("Error creating node", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/relationships")
async def create_relationship(rel_data: RelationshipRequest):
    """Create a relationship between nodes"""
    try:
        with neo4j_driver.session() as session:
            query = """
            MATCH (a), (b)
            WHERE a.id = $source_id AND b.id = $target_id
            CREATE (a)-[r:""" + rel_data.relationship_type + """ $properties]->(b)
            RETURN r
            """
            result = session.run(query, {
                "source_id": rel_data.source_id,
                "target_id": rel_data.target_id,
                "properties": rel_data.properties
            })

            return {"success": True, "relationship": "created"}

    except Exception as e:
        logger.error("Error creating relationship", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query")
async def execute_query(query_data: QueryRequest):
    """Execute a Cypher query"""
    try:
        with neo4j_driver.session() as session:
            result = session.run(query_data.query, query_data.parameters)
            records = [record.data() for record in result]

            return {"success": True, "results": records}

    except Exception as e:
        logger.error("Error executing query", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def get_graph_stats():
    """Get graph statistics"""
    try:
        with neo4j_driver.session() as session:
            # Count nodes
            node_result = session.run("MATCH (n) RETURN count(n) as node_count")
            node_count = node_result.single()["node_count"]

            # Count relationships
            rel_result = session.run("MATCH ()-[r]->() RETURN count(r) as rel_count")
            rel_count = rel_result.single()["rel_count"]

            return {
                "nodes": node_count,
                "relationships": rel_count,
                "timestamp": datetime.utcnow().isoformat()
            }

    except Exception as e:
        logger.error("Error getting graph stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)