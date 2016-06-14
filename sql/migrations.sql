This is not meant to be run directly.

-- migration #1
CREATE TABLE db_meta (key text PRIMARY KEY, value jsonb);
INSERT INTO db_meta (key, value) VALUES ('schema_version', '1'::jsonb);

-- migration #2
CREATE OR REPLACE VIEW current_takes AS
    SELECT * FROM (
         SELECT DISTINCT ON (member, team) t.*
           FROM takes t
       ORDER BY member, team, mtime DESC
    ) AS anon WHERE amount IS NOT NULL;
ALTER TABLE participants DROP COLUMN is_suspicious;

-- migration #3
ALTER TABLE paydays ADD COLUMN nusers bigint NOT NULL DEFAULT 0,
                    ADD COLUMN week_deposits numeric(35,2) NOT NULL DEFAULT 0,
                    ADD COLUMN week_withdrawals numeric(35,2) NOT NULL DEFAULT 0;
WITH week_exchanges AS (
         SELECT e.*, (
                    SELECT p.id
                      FROM paydays p
                     WHERE e.timestamp < p.ts_start
                  ORDER BY p.ts_start DESC
                     LIMIT 1
                ) AS payday_id
           FROM exchanges e
          WHERE status <> 'failed'
     )
UPDATE paydays p
   SET nusers = (
           SELECT count(*)
             FROM participants
            WHERE kind IN ('individual', 'organization')
              AND join_time < p.ts_start
              AND status = 'active'
       )
     , week_deposits = (
           SELECT COALESCE(sum(amount), 0)
             FROM week_exchanges
            WHERE payday_id = p.id
              AND amount > 0
       )
     , week_withdrawals = (
           SELECT COALESCE(-sum(amount), 0)
             FROM week_exchanges
            WHERE payday_id = p.id
              AND amount < 0
       );

-- migration #4
CREATE TABLE app_conf (key text PRIMARY KEY, value jsonb);

-- migration #5
UPDATE elsewhere
   SET avatar_url = regexp_replace(avatar_url,
          '^https://secure\.gravatar\.com/',
          'https://seccdn.libravatar.org/'
       )
 WHERE avatar_url LIKE '%//secure.gravatar.com/%';
UPDATE participants
   SET avatar_url = regexp_replace(avatar_url,
          '^https://secure\.gravatar\.com/',
          'https://seccdn.libravatar.org/'
       )
 WHERE avatar_url LIKE '%//secure.gravatar.com/%';
ALTER TABLE participants ADD COLUMN avatar_src text;
ALTER TABLE participants ADD COLUMN avatar_email text;

-- migration #6
ALTER TABLE exchanges ADD COLUMN vat numeric(35,2) NOT NULL DEFAULT 0;
ALTER TABLE exchanges ALTER COLUMN vat DROP DEFAULT;

-- migration #7
CREATE TABLE e2e_transfers
( id           bigserial      PRIMARY KEY
, origin       bigint         NOT NULL REFERENCES exchanges
, withdrawal   bigint         NOT NULL REFERENCES exchanges
, amount       numeric(35,2)  NOT NULL CHECK (amount > 0)
);
ALTER TABLE exchanges ADD CONSTRAINT exchanges_amount_check CHECK (amount <> 0);

-- migration #8
ALTER TABLE participants ADD COLUMN profile_nofollow boolean DEFAULT TRUE;

-- migration #9
CREATE OR REPLACE VIEW sponsors AS
    SELECT *
      FROM participants p
     WHERE status = 'active'
       AND kind = 'organization'
       AND giving > receiving
       AND giving >= 10
       AND NOT profile_nofollow;

-- migration #10
ALTER TABLE notification_queue ADD COLUMN is_new boolean NOT NULL DEFAULT TRUE;

-- migration #11
ALTER TYPE payment_net ADD VALUE 'mango-bw' BEFORE 'mango-cc';

-- migration #12
ALTER TABLE communities ADD COLUMN is_hidden boolean NOT NULL DEFAULT FALSE;

-- migration #13
ALTER TABLE participants ADD COLUMN profile_noindex boolean NOT NULL DEFAULT FALSE;
ALTER TABLE participants ADD COLUMN hide_from_lists boolean NOT NULL DEFAULT FALSE;

-- migration #14
DROP VIEW sponsors;
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
       AND NOT profile_nofollow;
DELETE FROM app_conf WHERE key = 'cache_static';
