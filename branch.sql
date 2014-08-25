BEGIN;

    CREATE INDEX communities_all ON communities (participant, slug, mtime DESC);

END;
