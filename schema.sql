-------------------------------------------------------------------------------
--                             million trillion trillion
--                             |         trillion trillion
--                             |         |               trillion
--                             |         |               |   billion
--                             |         |               |   |   million
--                             |         |               |   |   |   thousand
--                             |         |               |   |   |   |
-- numeric(35,2) maxes out at $999,999,999,999,999,999,999,999,999,999,999.00.


-------------------------------------------------------------------------------
-- Create the initial structure.

CREATE EXTENSION hstore;

CREATE TABLE participants
( id                    text                        PRIMARY KEY
, statement             text                        DEFAULT ''

, stripe_customer_id    text                        DEFAULT NULL
, last_bill_result      text                        DEFAULT NULL

, session_token         text                        UNIQUE DEFAULT NULL
, session_expires       timestamp with time zone    DEFAULT CURRENT_TIMESTAMP

, ctime                 timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, claimed_time          timestamp with time zone    DEFAULT NULL
, is_admin              boolean                     NOT NULL DEFAULT FALSE
, shares_giving         boolean                     NOT NULL DEFAULT TRUE

-- If this isn't NULL then it means one participant was folded into another
-- and all requests for this participant should be redirected to the other.
, redirect              text            DEFAULT NULL REFERENCES participants

-- The participants balance is expected to be receipts - disbursements. It is
-- stored here as an optimization and sanity check.
, balance               numeric(35,2)               DEFAULT 0.0
, pending               numeric(35,2)               DEFAULT NULL
 );

CREATE TABLE social_network_users
( id                    serial          PRIMARY KEY
, network               text            NOT NULL
, user_id               text            NOT NULL
, user_info             hstore
, is_locked             boolean         NOT NULL DEFAULT FALSE
, participant_id        text            DEFAULT NULL REFERENCES participants ON DELETE RESTRICT
, UNIQUE(network, user_id)
 );

-- tips -- all times a participant elects to tip another
CREATE TABLE tips
( id                    serial                      PRIMARY KEY
, ctime                 timestamp with time zone    NOT NULL
, mtime                 timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, tipper                text                        NOT NULL REFERENCES participants ON DELETE RESTRICT
, tippee                text                        NOT NULL REFERENCES participants ON DELETE RESTRICT
, amount                numeric(35,2)               NOT NULL
 );

-- transfers -- balance transfers from one user to another
CREATE TABLE transfers
( id                    serial                      PRIMARY KEY
, timestamp             timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, tipper                text                        NOT NULL REFERENCES participants ON DELETE RESTRICT
, tippee                text                        NOT NULL REFERENCES participants ON DELETE RESTRICT
, amount                numeric(35,2)               NOT NULL
 );

-- paydays -- payday events, stats about them
CREATE TABLE paydays
( id                    serial                      PRIMARY KEY
, ts_start              timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, ts_end                timestamp with time zone    UNIQUE NOT NULL DEFAULT '1970-01-01T00:00:00+00'::timestamptz
, nparticipants         bigint                      DEFAULT 0
, ntippers              bigint                      DEFAULT 0
, ntips                 bigint                      DEFAULT 0
, ntransfers            bigint                      DEFAULT 0
, transfer_volume       numeric(35,2)               DEFAULT 0.00
, ncc_failing           bigint                      DEFAULT 0
, ncc_missing           bigint                      DEFAULT 0
, nexchanges            bigint                      DEFAULT 0
, exchange_volume       numeric(35,2)               DEFAULT 0.00
, exchange_fees_volume  numeric(35,2)               DEFAULT 0.00
 );

-- exchanges -- when a participant moves cash between Gittip and their bank
CREATE TABLE exchanges
( id                    serial                      PRIMARY KEY
, timestamp             timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, amount                numeric(35,2)               NOT NULL
, fee                   numeric(35,2)               NOT NULL
, participant_id        text                        NOT NULL REFERENCES participants ON DELETE RESTRICT
 );


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/128

ALTER TABLE participants ADD COLUMN anonymous bool NOT NULL DEFAULT FALSE;
ALTER TABLE participants DROP COLUMN shares_giving;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/110

ALTER TABLE participants ADD COLUMN goal numeric(35,2) DEFAULT NULL;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/78

ALTER TABLE participants ADD COLUMN balanced_account_uri text DEFAULT NULL;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/161

ALTER TABLE participants ADD CONSTRAINT min_balance CHECK(balance >= 0);


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/35

ALTER TABLE participants ALTER COLUMN statement SET NOT NULL;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/22

ALTER TABLE participants ADD COLUMN last_ach_result text DEFAULT NULL;

ALTER TABLE paydays RENAME COLUMN nexchanges            TO ncharges;
ALTER TABLE paydays RENAME COLUMN exchange_volume       TO charge_volume;
ALTER TABLE paydays RENAME COLUMN exchange_fees_volume  TO charge_fees_volume;

ALTER TABLE paydays ADD COLUMN nachs            bigint          DEFAULT 0;
ALTER TABLE paydays ADD COLUMN ach_volume       numeric(35,2)   DEFAULT 0.00;
ALTER TABLE paydays ADD COLUMN ach_fees_volume  numeric(35,2)   DEFAULT 0.00;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/80

-- The redirect column ended up being YAGNI. I'm dropping it here because
-- it's implicated in constraints that we'd otherwise have to alter below.

ALTER TABLE participants DROP redirect;

BEGIN;

    -- We need to be able to change participant_id and have that cascade out to
    -- other tables. Let's do this in a transaction, just for kicks. Kinda
    -- gives me the willies to be changing constraints like this. I think it's
    -- because I never created the constraints so explicitly in the first
    -- place. The below is copied / pasted / edited from `\d participants`.
    -- I *think* I'm doing this right. :^O

    ALTER TABLE "exchanges" DROP CONSTRAINT "exchanges_participant_id_fkey";
    ALTER TABLE "exchanges" ADD CONSTRAINT "exchanges_participant_id_fkey"
        FOREIGN KEY (participant_id) REFERENCES participants(id)
        ON UPDATE CASCADE ON DELETE RESTRICT;

    ALTER TABLE "social_network_users" DROP CONSTRAINT "social_network_users_participant_id_fkey";
    ALTER TABLE "social_network_users" ADD CONSTRAINT "social_network_users_participant_id_fkey"
        FOREIGN KEY (participant_id) REFERENCES participants(id)
        ON UPDATE CASCADE ON DELETE RESTRICT;

    ALTER TABLE "tips" DROP CONSTRAINT "tips_tippee_fkey";
    ALTER TABLE "tips" ADD CONSTRAINT "tips_tippee_fkey"
        FOREIGN KEY (tippee) REFERENCES participants(id)
        ON UPDATE CASCADE ON DELETE RESTRICT;

    ALTER TABLE "tips" DROP CONSTRAINT "tips_tipper_fkey";
    ALTER TABLE "tips" ADD CONSTRAINT "tips_tipper_fkey"
        FOREIGN KEY (tipper) REFERENCES participants(id)
        ON UPDATE CASCADE ON DELETE RESTRICT;

    ALTER TABLE "transfers" DROP CONSTRAINT "transfers_tippee_fkey";
    ALTER TABLE "transfers" ADD CONSTRAINT "transfers_tippee_fkey"
        FOREIGN KEY (tippee) REFERENCES participants(id)
        ON UPDATE CASCADE ON DELETE RESTRICT;

    ALTER TABLE "transfers" DROP CONSTRAINT "transfers_tipper_fkey";
    ALTER TABLE "transfers" ADD CONSTRAINT "transfers_tipper_fkey"
        FOREIGN KEY (tipper) REFERENCES participants(id)
        ON UPDATE CASCADE ON DELETE RESTRICT;

END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/35
-- https://github.com/gittip/www.gittip.com/issues/170

ALTER TABLE participants ALTER COLUMN balance SET NOT NULL;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/350

ALTER TABLE participants ADD COLUMN payin_suspended bool NOT NULL DEFAULT FALSE;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/354

ALTER TABLE participants ADD COLUMN is_suspicious bool DEFAULT NULL;
UPDATE participants SET is_suspicious=true WHERE payin_suspended;
ALTER TABLE participants DROP COLUMN payin_suspended;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/406

ALTER TABLE social_network_users RENAME TO elsewhere;
ALTER TABLE elsewhere RENAME COLUMN network TO platform;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/406

CREATE TABLE absorptions
( id                    serial                      PRIMARY KEY
, timestamp             timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, absorbed_by           text                        NOT NULL REFERENCES participants ON DELETE RESTRICT
, absorbed              text                        NOT NULL REFERENCES participants ON DELETE RESTRICT
 );


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/406

-- Decided to change this. Easier to drop and recreate at this point.
DROP TABLE absorptions;
CREATE TABLE absorptions
( id                    serial                      PRIMARY KEY
, timestamp             timestamp with time zone    NOT NULL
    DEFAULT CURRENT_TIMESTAMP

, absorbed_was          text                        NOT NULL
    -- Not a foreign key!

, absorbed_by           text                        NOT NULL
    REFERENCES participants ON DELETE RESTRICT ON UPDATE CASCADE

, archived_as           text                        NOT NULL
    REFERENCES participants ON DELETE RESTRICT ON UPDATE RESTRICT
    -- For absorbed we actually want ON UPDATE RESTRICT as a sanity check:
    -- noone should be changing participant_ids of absorbed accounts.
 );


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/406

-- Let's clean up the naming of the constraints on the elsewhere table.
BEGIN;

    ALTER TABLE elsewhere DROP CONSTRAINT "social_network_users_pkey";
    ALTER TABLE elsewhere ADD CONSTRAINT "elsewhere_pkey"
        PRIMARY KEY (id);

    ALTER TABLE elsewhere DROP constraint "social_network_users_network_user_id_key";
    ALTER TABLE elsewhere ADD constraint "elsewhere_platform_user_id_key"
        UNIQUE (platform, user_id);

    ALTER TABLE elsewhere DROP constraint "social_network_users_participant_id_fkey";
    ALTER TABLE elsewhere ADD constraint "elsewhere_participant_id_fkey"
        FOREIGN KEY (participant_id) REFERENCES participants(id)
        ON UPDATE CASCADE ON DELETE RESTRICT;

END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/419

ALTER TABLE paydays ADD COLUMN nach_failures bigint DEFAULT 0;
ALTER TABLE paydays RENAME COLUMN nach_failures TO nach_failing; -- double oops


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/35
-- https://github.com/gittip/www.gittip.com/issues/406

ALTER TABLE elsewhere ALTER COLUMN participant_id SET NOT NULL;

-- Every account elsewhere must have at least a stub participant account in
-- Gittip. However, not every participant must have an account elsewhere. A
-- participant without a connected account elsewhere will have no way to login
-- to Gittip. It will be considered "archived."


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/406

-- Gittip participants can only connect one account per platform at a time.

ALTER TABLE elsewhere ADD CONSTRAINT "elsewhere_platform_participant_id_key"
    UNIQUE (platform, participant_id);


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/53

ALTER TABLE exchanges ADD COLUMN recorder text DEFAULT NULL
        REFERENCES participants(id)
        ON UPDATE CASCADE ON DELETE RESTRICT;

ALTER TABLE exchanges ADD COLUMN note text DEFAULT NULL;


-------------------------------------------------------------------------------
--- https://github.com/gittip/www.gittip.com/issues/545
create view goal_summary as SELECT tippee as id, goal, (amount/goal) * 100  as  percentage, statement,  sum(amount) as amount
         FROM (    SELECT DISTINCT ON (tipper, tippee) tippee, amount
                     FROM tips
                     JOIN participants p ON p.id = tipper
                     JOIN participants p2 ON p2.id = tippee
                    WHERE p.last_bill_result = ''
                      AND p2.claimed_time IS NOT NULL
                 ORDER BY tipper, tippee, mtime DESC
               ) AS tips_agg
         join participants p3 on p3.id = tips_agg.tippee
     GROUP BY tippee, goal, percentage, statement
;


-------------------------------------------------------------------------------
--- https://github.com/gittip/www.gittip.com/issues/778

DROP VIEW goal_summary;
CREATE VIEW goal_summary AS
  SELECT tippee as id
       , goal
       , CASE goal WHEN 0 THEN 0 ELSE (amount / goal) * 100 END AS percentage
       , statement
       , sum(amount) as amount
    FROM ( SELECT DISTINCT ON (tipper, tippee) tippee, amount
                         FROM tips
                         JOIN participants p ON p.id = tipper
                         JOIN participants p2 ON p2.id = tippee
                        WHERE p.last_bill_result = ''
                          AND p2.claimed_time IS NOT NULL
                     ORDER BY tipper, tippee, mtime DESC
          ) AS tips_agg
    JOIN participants p3 ON p3.id = tips_agg.tippee
   WHERE goal > 0
GROUP BY tippee, goal, percentage, statement;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/141

-- Create a goals table to track all goals a participant has stated over time.
CREATE TABLE goals
( id                    serial                      PRIMARY KEY
, ctime                 timestamp with time zone    NOT NULL
, mtime                 timestamp with time zone    NOT NULL
                                                    DEFAULT CURRENT_TIMESTAMP
, participant           text                        NOT NULL
                                                    REFERENCES participants
                                                    ON UPDATE CASCADE
                                                    ON DELETE RESTRICT
, amount                numeric(35,2)               DEFAULT NULL
 );

--- Migrate data from goal column of participants over to new goals table.
INSERT INTO goals (ctime, mtime, participant, amount)
     SELECT CURRENT_TIMESTAMP
          , CURRENT_TIMESTAMP
          , id
          , goal
       FROM participants
      WHERE goal IS NOT null;

-- Create a view to make it easy to get the latest goal.
CREATE VIEW latest_goals AS

      SELECT DISTINCT ON (participant) *
        FROM goals
    ORDER BY participant, mtime DESC;

-- Recreate the goal_summary view to use the new goals table.
DROP VIEW goal_summary;
CREATE VIEW goal_summary AS
  SELECT tippee as id
       , latest_goals.amount as goal
       , CASE goal WHEN 0 THEN 0 ELSE (amount / goal) * 100 END AS percentage
       , statement
       , sum(amount) as amount
    FROM ( SELECT DISTINCT ON (tipper, tippee) tippee, amount
                         FROM tips
                         JOIN participants p ON p.id = tipper
                         JOIN participants p2 ON p2.id = tippee
                        WHERE p.last_bill_result = ''
                          AND p2.claimed_time IS NOT NULL
                     ORDER BY tipper, tippee, mtime DESC
          ) AS tips_agg
    JOIN latest_goals ON latest_goals.participant = tips_agg.tippee
   WHERE latest_goals.goal > 0
GROUP BY tippee, goal, percentage, statement;

ALTER TABLE participants DROP COLUMN goal;
