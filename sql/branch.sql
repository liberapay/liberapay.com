BEGIN;

\i sql/update_counts.sql

DROP TRIGGER update_community_nmembers ON community_memberships;
CREATE TRIGGER update_community_nmembers
    AFTER INSERT OR UPDATE OR DELETE ON community_memberships
    FOR EACH ROW
    EXECUTE PROCEDURE update_community_nmembers();

DROP TRIGGER update_nsubscribers ON subscriptions;
CREATE TRIGGER update_nsubscribers
    AFTER INSERT OR UPDATE OR DELETE ON subscriptions
    FOR EACH ROW
    EXECUTE PROCEDURE update_nsubscribers();

END;

BEGIN;

UPDATE communities AS c
   SET nmembers = (
           SELECT count(*)
             FROM community_memberships m
            WHERE m.community = c.id
              AND m.is_on
       )
 WHERE nmembers <> (
           SELECT count(*)
             FROM community_memberships m
            WHERE m.community = c.id
              AND m.is_on
       );

UPDATE participants AS p
   SET nsubscribers = (
           SELECT count(*)
             FROM subscriptions s
            WHERE s.publisher = p.id
              AND s.is_on
       )
 WHERE nsubscribers <> (
           SELECT count(*)
             FROM subscriptions s
            WHERE s.publisher = p.id
              AND s.is_on
       );

END;
