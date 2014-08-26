BEGIN;

    CREATE INDEX communities_all ON communities (participant, slug, mtime DESC);

    DROP VIEW community_summary;
    DROP VIEW current_communities;

    CREATE VIEW current_communities AS
        SELECT DISTINCT ON (participant, slug) c.*
          FROM communities c
      ORDER BY participant, slug, mtime DESC;

    CREATE VIEW community_summary AS
        SELECT max(name) AS name -- gotta pick one, this is good enough for now
             , slug
             , count(participant) AS nmembers
          FROM current_communities
          JOIN participants p ON p.username = participant
         WHERE is_member
           AND p.is_suspicious IS NOT true
      GROUP BY slug
      ORDER BY nmembers DESC, slug;

END;
