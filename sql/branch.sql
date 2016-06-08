DROP VIEw sponsors;

ALTER TABLE participants ADD COLUMN privileges int NOT NULL DEFAULT 0;
UPDATE participants SET privileges = 1 WHERE is_admin;
ALTER TABLE participants DROP COLUMN is_admin;

CREATE OR REPLACE VIEW sponsors AS
    SELECT *
      FROM participants p
     WHERE status = 'active'
       AND kind = 'organization'
       AND giving > receiving
       AND giving >= 10
       AND NOT profile_nofollow
    ;
