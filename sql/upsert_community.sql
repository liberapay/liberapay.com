CREATE OR REPLACE FUNCTION upsert_community() RETURNS trigger AS $$
    DECLARE
        is_member boolean;
        delta int = CASE WHEN NEW.is_member THEN 1 ELSE -1 END;
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
               SET nmembers = nmembers + delta
             WHERE slug = NEW.slug
               AND nmembers + delta > 0;
            EXIT WHEN FOUND;
            IF (NEW.is_member) THEN
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
            ELSE
                DELETE FROM communities WHERE slug = NEW.slug AND nmembers = 1;
                EXIT WHEN FOUND;
            END IF;
        END LOOP;
        RETURN NEW;
    END;
$$ LANGUAGE plpgsql;
