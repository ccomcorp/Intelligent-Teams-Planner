-- Migration: Add vector support for embeddings
-- This demonstrates pgvector usage for future AI features

-- Add embedding columns to existing tables
-- Note: These columns are optional and will be used for future AI features

-- Add embeddings to plans table for semantic search
ALTER TABLE plans ADD COLUMN IF NOT EXISTS title_embedding vector(384);
ALTER TABLE plans ADD COLUMN IF NOT EXISTS description_embedding vector(384);

-- Add embeddings to tasks table for semantic search
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS title_embedding vector(384);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS description_embedding vector(384);

-- Create new table for document embeddings (future feature)
CREATE TABLE IF NOT EXISTS document_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id VARCHAR(255) NOT NULL,
    document_type VARCHAR(50) NOT NULL, -- 'plan', 'task', 'comment', etc.
    content_hash VARCHAR(64) NOT NULL,
    embedding vector(384) NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for vector similarity search
CREATE INDEX IF NOT EXISTS idx_plans_title_embedding ON plans USING ivfflat (title_embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_plans_description_embedding ON plans USING ivfflat (description_embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_tasks_title_embedding ON tasks USING ivfflat (title_embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_tasks_description_embedding ON tasks USING ivfflat (description_embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_document_embeddings_vector ON document_embeddings USING ivfflat (embedding vector_cosine_ops);

-- Create indexes for document_embeddings table
CREATE INDEX IF NOT EXISTS idx_document_embeddings_document_id ON document_embeddings(document_id);
CREATE INDEX IF NOT EXISTS idx_document_embeddings_document_type ON document_embeddings(document_type);
CREATE INDEX IF NOT EXISTS idx_document_embeddings_content_hash ON document_embeddings(content_hash);
CREATE INDEX IF NOT EXISTS idx_document_embeddings_created_at ON document_embeddings(created_at);

-- Function for semantic search across plans
CREATE OR REPLACE FUNCTION semantic_search_plans(
    query_embedding vector(384),
    similarity_threshold FLOAT DEFAULT 0.7,
    limit_param INTEGER DEFAULT 10,
    user_id_param VARCHAR DEFAULT NULL
)
RETURNS TABLE(
    plan_id UUID,
    title VARCHAR,
    description TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        p.id as plan_id,
        p.title,
        p.description,
        (1 - (p.title_embedding <=> query_embedding)) as similarity
    FROM plans p
    WHERE
        (user_id_param IS NULL OR p.owner_id = user_id_param)
        AND p.is_archived = false
        AND p.title_embedding IS NOT NULL
        AND (1 - (p.title_embedding <=> query_embedding)) >= similarity_threshold
    ORDER BY p.title_embedding <=> query_embedding
    LIMIT limit_param;
END;
$$ LANGUAGE plpgsql;

-- Function for semantic search across tasks
CREATE OR REPLACE FUNCTION semantic_search_tasks(
    query_embedding vector(384),
    similarity_threshold FLOAT DEFAULT 0.7,
    limit_param INTEGER DEFAULT 10,
    plan_id_param VARCHAR DEFAULT NULL
)
RETURNS TABLE(
    task_id UUID,
    title VARCHAR,
    description TEXT,
    plan_title VARCHAR,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.id as task_id,
        t.title,
        t.description,
        p.title as plan_title,
        (1 - (t.title_embedding <=> query_embedding)) as similarity
    FROM tasks t
    JOIN plans p ON t.plan_graph_id = p.graph_id
    WHERE
        (plan_id_param IS NULL OR t.plan_graph_id = plan_id_param)
        AND t.title_embedding IS NOT NULL
        AND (1 - (t.title_embedding <=> query_embedding)) >= similarity_threshold
    ORDER BY t.title_embedding <=> query_embedding
    LIMIT limit_param;
END;
$$ LANGUAGE plpgsql;

-- Function for hybrid search (combining full-text and semantic search)
CREATE OR REPLACE FUNCTION hybrid_search_content(
    search_query TEXT,
    query_embedding vector(384) DEFAULT NULL,
    user_id_param VARCHAR DEFAULT NULL,
    limit_param INTEGER DEFAULT 20,
    semantic_weight FLOAT DEFAULT 0.5
)
RETURNS TABLE(
    content_type VARCHAR,
    id UUID,
    title VARCHAR,
    description TEXT,
    text_rank FLOAT,
    semantic_score FLOAT,
    combined_score FLOAT
) AS $$
BEGIN
    RETURN QUERY
    WITH text_search AS (
        -- Full-text search results
        SELECT
            'plan'::VARCHAR as content_type,
            p.id,
            p.title,
            p.description,
            ts_rank(to_tsvector('english', p.title || ' ' || COALESCE(p.description, '')), plainto_tsquery('english', search_query)) as text_rank,
            CASE
                WHEN p.title_embedding IS NOT NULL AND query_embedding IS NOT NULL
                THEN (1 - (p.title_embedding <=> query_embedding))
                ELSE 0
            END as semantic_score
        FROM plans p
        WHERE
            (user_id_param IS NULL OR p.owner_id = user_id_param)
            AND p.is_archived = false
            AND to_tsvector('english', p.title || ' ' || COALESCE(p.description, '')) @@ plainto_tsquery('english', search_query)

        UNION ALL

        SELECT
            'task'::VARCHAR as content_type,
            t.id,
            t.title,
            t.description,
            ts_rank(to_tsvector('english', t.title || ' ' || COALESCE(t.description, '')), plainto_tsquery('english', search_query)) as text_rank,
            CASE
                WHEN t.title_embedding IS NOT NULL AND query_embedding IS NOT NULL
                THEN (1 - (t.title_embedding <=> query_embedding))
                ELSE 0
            END as semantic_score
        FROM tasks t
        JOIN plans p ON t.plan_graph_id = p.graph_id
        WHERE
            (user_id_param IS NULL OR p.owner_id = user_id_param)
            AND to_tsvector('english', t.title || ' ' || COALESCE(t.description, '')) @@ plainto_tsquery('english', search_query)
    )
    SELECT
        ts.content_type,
        ts.id,
        ts.title,
        ts.description,
        ts.text_rank,
        ts.semantic_score,
        -- Combined score: weighted average of text and semantic scores
        ((1 - semantic_weight) * ts.text_rank + semantic_weight * ts.semantic_score) as combined_score
    FROM text_search ts
    ORDER BY combined_score DESC
    LIMIT limit_param;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to update updated_at for document_embeddings
CREATE TRIGGER update_document_embeddings_updated_at
    BEFORE UPDATE ON document_embeddings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE document_embeddings IS 'Stores vector embeddings for semantic search capabilities';
COMMENT ON COLUMN plans.title_embedding IS 'Vector embedding of plan title for semantic search';
COMMENT ON COLUMN plans.description_embedding IS 'Vector embedding of plan description for semantic search';
COMMENT ON COLUMN tasks.title_embedding IS 'Vector embedding of task title for semantic search';
COMMENT ON COLUMN tasks.description_embedding IS 'Vector embedding of task description for semantic search';

-- Grant permissions on new table
GRANT SELECT, INSERT, UPDATE, DELETE ON document_embeddings TO itp_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO itp_user;