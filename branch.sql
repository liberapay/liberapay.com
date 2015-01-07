BEGIN;

-- Index user and community names

CREATE EXTENSION pg_trgm;

CREATE INDEX username_trgm_idx ON participants
    USING gist(username_lower gist_trgm_ops)
    WHERE claimed_time IS NOT NULL AND NOT is_closed;

CREATE INDEX community_trgm_idx ON communities
    USING gist(name gist_trgm_ops);

-- Index statements

ALTER TABLE statements ADD COLUMN search_vector tsvector;
ALTER TABLE statements ADD COLUMN search_conf regconfig;

CREATE INDEX statements_fts_idx ON statements USING gist(search_vector);

CREATE TRIGGER search_vector_update
    BEFORE INSERT OR UPDATE ON statements
    FOR EACH ROW EXECUTE PROCEDURE
    tsvector_update_trigger_column(search_vector, search_conf, content);

-- Initialize search_conf column

CREATE TEMP TABLE languages
( lang_code    text       PRIMARY KEY
, search_conf  regconfig  NOT NULL
);

INSERT INTO languages
VALUES ('da', 'danish'),
       ('de', 'german'),
       ('en', 'english'),
       ('es', 'spanish'),
       ('fi', 'finnish'),
       ('fr', 'french'),
       ('hu', 'hungarian'),
       ('it', 'italian'),
       ('nb', 'norwegian'),
       ('nl', 'dutch'),
       ('nn', 'norwegian'),
       ('pt', 'portuguese'),
       ('ro', 'romanian'),
       ('ru', 'russian'),
       ('sv', 'swedish'),
       ('tr', 'turkish');

UPDATE statements SET search_conf = COALESCE((SELECT search_conf FROM languages WHERE lang_code = lang), 'simple');
ALTER TABLE statements ALTER COLUMN search_conf SET NOT NULL;

END;
