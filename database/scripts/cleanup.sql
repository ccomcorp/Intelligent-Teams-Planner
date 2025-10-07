-- Database cleanup and maintenance scripts
-- Run these periodically to maintain database performance

-- Clean up expired tokens (run daily)
SELECT cleanup_expired_tokens() as expired_tokens_cleaned;

-- Clean up old conversation contexts (run weekly)
SELECT cleanup_old_conversations() as old_conversations_cleaned;

-- Analyze tables for optimal query performance (run weekly)
ANALYZE users;
ANALYZE plans;
ANALYZE tasks;
ANALYZE token_storage;
ANALYZE conversation_contexts;
ANALYZE document_embeddings;

-- Vacuum tables to reclaim space (run weekly)
VACUUM ANALYZE users;
VACUUM ANALYZE plans;
VACUUM ANALYZE tasks;
VACUUM ANALYZE token_storage;
VACUUM ANALYZE conversation_contexts;
VACUUM ANALYZE document_embeddings;

-- Reindex vector indexes if they become inefficient (run monthly)
-- Note: Only run these if you notice performance degradation
-- REINDEX INDEX idx_plans_title_embedding;
-- REINDEX INDEX idx_plans_description_embedding;
-- REINDEX INDEX idx_tasks_title_embedding;
-- REINDEX INDEX idx_tasks_description_embedding;
-- REINDEX INDEX idx_document_embeddings_vector;

-- Generate database statistics report
SELECT
    'Database Statistics' as report_type,
    json_build_object(
        'total_users', (SELECT COUNT(*) FROM users),
        'active_users_last_30_days', (SELECT COUNT(*) FROM users WHERE created_at > CURRENT_DATE - INTERVAL '30 days'),
        'total_plans', (SELECT COUNT(*) FROM plans WHERE is_archived = false),
        'total_archived_plans', (SELECT COUNT(*) FROM plans WHERE is_archived = true),
        'total_tasks', (SELECT COUNT(*) FROM tasks),
        'completed_tasks', (SELECT COUNT(*) FROM tasks WHERE is_completed = true),
        'overdue_tasks', (SELECT COUNT(*) FROM tasks WHERE due_date < CURRENT_DATE AND is_completed = false),
        'active_tokens', (SELECT COUNT(*) FROM token_storage WHERE expires_at > CURRENT_TIMESTAMP),
        'active_conversations', (SELECT COUNT(*) FROM conversation_contexts WHERE last_activity > CURRENT_DATE - INTERVAL '7 days'),
        'database_size', pg_size_pretty(pg_database_size(current_database())),
        'last_updated', CURRENT_TIMESTAMP
    ) as statistics;

-- Performance monitoring query
SELECT
    schemaname,
    tablename,
    n_tup_ins as inserts,
    n_tup_upd as updates,
    n_tup_del as deletes,
    n_live_tup as live_tuples,
    n_dead_tup as dead_tuples,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;