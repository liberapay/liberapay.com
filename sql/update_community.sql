CREATE OR REPLACE FUNCTION update_community_nmembers() RETURNS trigger AS $$
    DECLARE
        old_is_on boolean = (CASE WHEN TG_OP = 'INSERT' THEN FALSE ELSE OLD.is_on END);
        new_is_on boolean = (CASE WHEN TG_OP = 'DELETE' THEN FALSE ELSE NEW.is_on END);
        delta int = CASE WHEN new_is_on THEN 1 ELSE -1 END;
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        IF (new_is_on = old_is_on) THEN
            RETURN (CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE rec END);
        END IF;
        UPDATE communities
           SET nmembers = nmembers + delta
         WHERE id = rec.community;
        RETURN rec;
    END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_community_nsubscribers() RETURNS trigger AS $$
    DECLARE
        old_is_on boolean = (CASE WHEN TG_OP = 'INSERT' THEN FALSE ELSE OLD.is_on END);
        new_is_on boolean = (CASE WHEN TG_OP = 'DELETE' THEN FALSE ELSE NEW.is_on END);
        delta int = CASE WHEN new_is_on THEN 1 ELSE -1 END;
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        IF (new_is_on = old_is_on) THEN
            RETURN (CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE rec END);
        END IF;
        UPDATE communities
           SET nsubscribers = nsubscribers + delta
         WHERE id = rec.community;
        RETURN rec;
    END;
$$ LANGUAGE plpgsql;
