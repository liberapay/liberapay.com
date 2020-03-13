BEGIN;
    DROP TRIGGER search_vector_update ON statements;
    ALTER TABLE statements
        ALTER COLUMN search_conf SET DATA TYPE text USING (search_conf::text),
        DROP COLUMN search_vector;
    DROP INDEX IF EXISTS statements_fts_idx;
    CREATE FUNCTION to_tsvector(text, text) RETURNS tsvector AS $$
        SELECT to_tsvector($1::regconfig, $2);
    $$ LANGUAGE sql STRICT IMMUTABLE;
    CREATE INDEX statements_fts_idx ON statements USING GIN (to_tsvector(search_conf, content));
END;
