CREATE OR REPLACE FUNCTION update_community_nmembers() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE communities
           SET nmembers = (
                   SELECT count(*)
                     FROM community_memberships m
                    WHERE m.community = rec.community
                      AND m.is_on
               )
         WHERE id = rec.community;
        RETURN rec;
    END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_nsubscribers() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE participants
           SET nsubscribers = (
                   SELECT count(*)
                     FROM subscriptions s
                    WHERE s.publisher = rec.publisher
                      AND s.is_on
               )
         WHERE id = rec.publisher;
        RETURN rec;
    END;
$$ LANGUAGE plpgsql;
