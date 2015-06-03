CREATE OR REPLACE FUNCTION upsert_community() RETURNS trigger AS $$
    DECLARE
        old_is_member boolean = (CASE WHEN TG_OP = 'INSERT' THEN FALSE ELSE OLD.is_member END);
        new_is_member boolean = (CASE WHEN TG_OP = 'DELETE' THEN FALSE ELSE NEW.is_member END);
        delta int = CASE WHEN new_is_member THEN 1 ELSE -1 END;
        cname text;
        rec record;
        i int;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        IF (new_is_member = old_is_member) THEN
            RETURN (CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE rec END);
        END IF;
        FOR i IN 1..10 LOOP
            UPDATE communities
               SET nmembers = nmembers + delta
             WHERE slug = rec.slug
               AND nmembers + delta > 0;
            IF (FOUND) THEN RETURN rec; END IF;
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
                RETURN rec;
            ELSE
                DELETE FROM communities WHERE slug = rec.slug AND nmembers = 1;
                IF (FOUND) THEN RETURN rec; END IF;
            END IF;
        END LOOP;
        RAISE 'upsert in communities failed';
    END;
$$ LANGUAGE plpgsql;
