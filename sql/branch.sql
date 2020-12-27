BEGIN;
    DROP INDEX username_trgm_idx;
    CREATE INDEX username_trgm_idx ON participants
        USING gin(lower(username) gin_trgm_ops)
        WHERE status = 'active'
          AND NOT username like '~%';
    DROP INDEX community_trgm_idx;
    CREATE INDEX community_trgm_idx ON communities
        USING gin(lower(name) gin_trgm_ops);
    DROP INDEX repositories_trgm_idx;
    CREATE INDEX repositories_trgm_idx ON repositories
        USING gin(lower(name) gin_trgm_ops)
        WHERE participant IS NOT NULL;
END;
