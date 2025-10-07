-- Intelligent Teams Planner Database Initialization
-- PostgreSQL with pgvector extension

-- Create the database (this is handled by docker-compose environment variables)
-- But we ensure the vector extension is available

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pgvector extension for vector embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Create planner user if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'itp_user') THEN
        CREATE USER itp_user WITH PASSWORD 'itp_password_2024';
    END IF;
END
$$;

-- Grant necessary permissions
GRANT CONNECT ON DATABASE intelligent_teams_planner TO itp_user;
GRANT USAGE ON SCHEMA public TO itp_user;
GRANT CREATE ON SCHEMA public TO itp_user;

-- Grant permissions on future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO itp_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO itp_user;

-- Set up connection limits
ALTER USER itp_user CONNECTION LIMIT 20;