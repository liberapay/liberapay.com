CREATE OR REPLACE FUNCTION upsert_community() RETURNS trigger AS $$
    DECLARE
        old_is_member boolean = (CASE WHEN TG_OP = 'INSERT' THEN FALSE ELSE OLD.is_member END);
        new_is_member boolean = (CASE WHEN TG_OP = 'DELETE' THEN FALSE ELSE NEW.is_member END);
        delta int = CASE WHEN new_is_member THEN 1 ELSE -1 END;
        cname text;
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        IF (new_is_member = old_is_member) THEN
            RETURN (CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE rec END);
        END IF;
        LOOP
            UPDATE communities
               SET nmembers = nmembers + delta
             WHERE slug = rec.slug
               AND nmembers + delta > 0;
            EXIT WHEN FOUND;
            IF (new_is_member) THEN
                BEGIN
                    INSERT INTO communities
                         VALUES (rec.slug, rec.name, 1, rec.ctime);
                EXCEPTION WHEN unique_violation THEN
                    GET STACKED DIAGNOSTICS cname = CONSTRAINT_NAME;
                    IF (cname = 'communities_slug_pkey') THEN
                        CONTINUE; -- Try again
                    ELSE
                        RAISE;
                    END IF;
                END;
                EXIT;
            ELSE
                DELETE FROM communities WHERE slug = rec.slug AND nmembers = 1;
                EXIT WHEN FOUND;
            END IF;
        END LOOP;
        RETURN rec;
    END;
$$ LANGUAGE plpgsql;
