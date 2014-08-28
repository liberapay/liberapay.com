BEGIN;

    CREATE TABLE community_members
    ( slug          text           NOT NULL
    , participant   bigint         NOT NULL REFERENCES participants(id)
    , ctime         timestamptz    NOT NULL
    , mtime         timestamptz    NOT NULL DEFAULT CURRENT_TIMESTAMP
    , name          text           NOT NULL
    , is_member     boolean        NOT NULL
     );

    CREATE INDEX community_members_idx
        ON community_members (slug, participant, mtime DESC);

    ALTER TABLE communities RENAME TO communities_;
    CREATE TABLE communities
    ( slug text PRIMARY KEY
    , name text UNIQUE NOT NULL
    , nmembers int NOT NULL
    , ctime timestamptz NOT NULL
    , CHECK (nmembers >= 0)
    );

    CREATE FUNCTION upsert_community() RETURNS trigger AS $$
        DECLARE
            is_member boolean;
        BEGIN
            IF (SELECT is_suspicious FROM participants WHERE id = NEW.participant) THEN
                RETURN NULL;
            END IF;
            is_member := (
                SELECT cur.is_member
                  FROM community_members cur
                 WHERE slug = NEW.slug
                   AND participant = NEW.participant
              ORDER BY mtime DESC
                 LIMIT 1
            );
            IF (is_member IS NULL AND NEW.is_member IS false OR NEW.is_member = is_member) THEN
                RETURN NULL;
            END IF;
            LOOP
                UPDATE communities
                   SET nmembers = nmembers + (CASE WHEN NEW.is_member THEN 1 ELSE -1 END)
                 WHERE slug = NEW.slug;
                EXIT WHEN FOUND;
                BEGIN
                    INSERT INTO communities
                         VALUES (NEW.slug, NEW.name, 1, NEW.ctime);
                EXCEPTION
                    WHEN unique_violation THEN
                        IF (CONSTRAINT_NAME = 'communities_slug_pkey') THEN
                            CONTINUE; -- Try again
                        ELSE
                            RAISE;
                        END IF;
                END;
                EXIT;
            END LOOP;
            RETURN NEW;
        END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER upsert_community BEFORE INSERT ON community_members
        FOR EACH ROW
        EXECUTE PROCEDURE upsert_community();

    INSERT INTO community_members
        SELECT slug, p.id, c.ctime, mtime, name, is_member
          FROM communities_ c
          JOIN participants p ON p.username = participant
      ORDER BY mtime ASC;

    -- This checks that nmembers is correct
    DO $$ BEGIN
        PERFORM c.slug, c.nmembers, cs.nmembers
           FROM communities c
           JOIN community_summary cs ON cs.slug = c.slug
          WHERE c.nmembers <> cs.nmembers;
        IF FOUND THEN RAISE EXCEPTION 'nmembers values do not match'; END IF;
    END; $$;

    DROP VIEW community_summary;
    DROP VIEW current_communities;
    DROP TABLE communities_;

    CREATE VIEW current_community_members AS
        SELECT DISTINCT ON (participant, slug) c.*
          FROM community_members c
      ORDER BY participant, slug, mtime DESC;

END;
