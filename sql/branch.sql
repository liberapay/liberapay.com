ALTER TABLE tips ADD COLUMN secrecy_level int;
-- 0 means public, 1 means private, 2 means secret

CREATE OR REPLACE VIEW current_tips AS
    SELECT DISTINCT ON (tipper, tippee) *
      FROM tips
  ORDER BY tipper, tippee, mtime DESC;

SELECT 'after deployment';

ALTER TABLE tips ALTER COLUMN secrecy_level DROP DEFAULT;
