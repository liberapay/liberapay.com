BEGIN;

    ALTER TABLE participants DROP COLUMN is_suspicious;

    CREATE OR REPLACE VIEW current_takes AS
        SELECT * FROM (
             SELECT DISTINCT ON (member, team) t.*
               FROM takes t
               JOIN participants p1 ON p1.id = member
               JOIN participants p2 ON p2.id = team
           ORDER BY member
                  , team
                  , mtime DESC
        ) AS anon WHERE amount IS NOT NULL;

END;
