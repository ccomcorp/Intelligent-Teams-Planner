"""
PostgreSQL client with connection pooling
Story 6.2 Task 1: Deploy Vector Database Infrastructure
"""

import asyncio
from typing import Optional
from urllib.parse import urlparse

import asyncpg
import numpy as np
import structlog
from pgvector.asyncpg import register_vector

logger = structlog.get_logger(__name__)


class PostgresClient:
    """
    Async PostgreSQL client with connection pooling
    Provides database connectivity for RAG service
    """

    def __init__(self, database_url: str, min_size: int = 5, max_size: int = 20):
        self.database_url = database_url
        self.min_size = min_size
        self.max_size = max_size
        self.pool: Optional[asyncpg.Pool] = None

        # Parse database URL for logging (without credentials)
        parsed = urlparse(database_url)
        self.host = parsed.hostname
        self.port = parsed.port
        self.database = parsed.path.lstrip('/')

    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        """Initialize connection with pgvector support"""
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await register_vector(conn)
        logger.debug("pgvector registered for connection")

    async def initialize(self) -> None:
        """Initialize connection pool"""
        try:
            logger.info("Initializing PostgreSQL connection pool",
                       host=self.host,
                       port=self.port,
                       database=self.database,
                       min_size=self.min_size,
                       max_size=self.max_size)

            # Create connection pool with pgvector initialization
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=self.min_size,
                max_size=self.max_size,
                command_timeout=60,
                init=self._init_connection,
                server_settings={
                    'jit': 'off',  # Disable JIT compilation for better performance on small queries
                    'application_name': 'rag_service'
                }
            )

            # Test connection
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")

            logger.info("PostgreSQL connection pool initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize PostgreSQL connection pool", error=str(e))
            raise

    async def close(self) -> None:
        """Close connection pool"""
        if self.pool:
            try:
                await self.pool.close()
                logger.info("PostgreSQL connection pool closed")
            except Exception as e:
                logger.error("Error closing PostgreSQL connection pool", error=str(e))

    async def execute_query(self, query: str, *args) -> str:
        """Execute a query that doesn't return data"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch_one(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch single row"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetch_all(self, query: str, *args) -> list[asyncpg.Record]:
        """Fetch all rows"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetch_value(self, query: str, *args):
        """Fetch single value"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def health_check(self) -> str:
        """Check database connectivity and performance"""
        try:
            if not self.pool:
                return "unhealthy"

            start_time = asyncio.get_event_loop().time()

            async with self.pool.acquire() as conn:
                # Test basic connectivity
                await conn.fetchval("SELECT 1")

                # Test pgvector extension
                extensions = await conn.fetch("""
                    SELECT extname, extversion
                    FROM pg_extension
                    WHERE extname = 'vector'
                """)

                if not extensions:
                    logger.warning("pgvector extension not found")
                    return "degraded"

                # Check connection pool health
                pool_stats = {
                    "size": self.pool.get_size(),
                    "min_size": self.pool.get_min_size(),
                    "max_size": self.pool.get_max_size(),
                    "idle_connections": self.pool.get_idle_size()
                }

            response_time = (asyncio.get_event_loop().time() - start_time) * 1000

            if response_time > 1000:  # > 1 second
                logger.warning("Slow database response", response_time_ms=response_time)
                return "degraded"

            logger.debug("Database health check passed",
                        response_time_ms=response_time,
                        pool_stats=pool_stats)

            return "healthy"

        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return "unhealthy"

    async def get_database_stats(self) -> dict:
        """Get database statistics"""
        try:
            async with self.pool.acquire() as conn:
                # Get database size
                db_size = await conn.fetchval("""
                    SELECT pg_size_pretty(pg_database_size(current_database()))
                """)

                # Get table stats for RAG tables
                table_stats = await conn.fetch("""
                    SELECT
                        schemaname,
                        tablename,
                        n_tup_ins as inserts,
                        n_tup_upd as updates,
                        n_tup_del as deletes,
                        n_live_tup as live_tuples,
                        n_dead_tup as dead_tuples
                    FROM pg_stat_user_tables
                    WHERE tablename LIKE 'rag_%'
                    ORDER BY tablename
                """)

                # Get connection stats
                connections = await conn.fetch("""
                    SELECT
                        state,
                        COUNT(*) as count
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                    GROUP BY state
                """)

                return {
                    "database_size": db_size,
                    "table_stats": [dict(row) for row in table_stats],
                    "connections": [dict(row) for row in connections],
                    "pool_stats": {
                        "size": self.pool.get_size(),
                        "min_size": self.pool.get_min_size(),
                        "max_size": self.pool.get_max_size(),
                        "idle_connections": self.pool.get_idle_size()
                    }
                }

        except Exception as e:
            logger.error("Failed to get database stats", error=str(e))
            return {"error": str(e)}

    async def vacuum_analyze(self, table_name: Optional[str] = None) -> None:
        """Run VACUUM ANALYZE on RAG tables for performance"""
        try:
            async with self.pool.acquire() as conn:
                if table_name:
                    if table_name.startswith('rag_'):
                        await conn.execute(f"VACUUM ANALYZE {table_name}")
                        logger.info("VACUUM ANALYZE completed", table=table_name)
                    else:
                        raise ValueError("Only RAG tables can be vacuumed")
                else:
                    # Vacuum all RAG tables
                    tables = ['rag_documents', 'rag_document_chunks', 'rag_search_analytics']
                    for table in tables:
                        await conn.execute(f"VACUUM ANALYZE {table}")
                        logger.debug("VACUUM ANALYZE completed", table=table)

                    logger.info("VACUUM ANALYZE completed for all RAG tables")

        except Exception as e:
            logger.error("VACUUM ANALYZE failed", error=str(e), table=table_name)
            raise

    async def create_backup_schema(self) -> str:
        """Create backup schema for data migration/testing"""
        try:
            import datetime
            backup_name = f"rag_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

            async with self.pool.acquire() as conn:
                await conn.execute(f"CREATE SCHEMA {backup_name}")

                # Copy tables to backup schema
                tables = ['rag_documents', 'rag_document_chunks', 'rag_search_analytics']
                for table in tables:
                    await conn.execute(f"""
                        CREATE TABLE {backup_name}.{table} AS
                        SELECT * FROM public.{table}
                    """)

                logger.info("Backup schema created", schema=backup_name)
                return backup_name

        except Exception as e:
            logger.error("Failed to create backup schema", error=str(e))
            raise