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
, goal                  numeric(35,2)               DEFAULT NULL
 );


BEGIN;

    -- Migrate data from goal column of participants over to new goals table.
    INSERT INTO goals (ctime, mtime, participant, goal)
         SELECT CURRENT_TIMESTAMP
              , CURRENT_TIMESTAMP
              , id
              , goal
           FROM participants
          WHERE goal IS NOT NULL;

    -- Create a rule to log changes to participant.goal into goals.
    CREATE RULE log_goal_changes
    AS ON UPDATE TO participants
              WHERE (OLD.goal IS NULL AND NOT NEW.goal IS NULL)
                 OR (NEW.goal IS NULL AND NOT OLD.goal IS NULL)
                 OR NEW.goal <> OLD.goal
                 DO
        INSERT INTO goals
                    (ctime, participant, goal)
             VALUES ( COALESCE (( SELECT ctime
                                    FROM goals
                                   WHERE participant=OLD.id
                                   LIMIT 1
                                 ), CURRENT_TIMESTAMP)
                    , OLD.id
                    , NEW.goal
                     );

END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/406

ALTER SEQUENCE social_network_users_id_seq RENAME TO elsewhere_id_seq;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/287


-- participants
ALTER TABLE participants RENAME COLUMN id TO username;


-- elsewhere
ALTER TABLE elsewhere RENAME COLUMN participant_id TO participant;

ALTER TABLE "elsewhere" DROP CONSTRAINT "elsewhere_participant_id_fkey";
ALTER TABLE "elsewhere" ADD CONSTRAINT "elsewhere_participant_fkey"
    FOREIGN KEY (participant) REFERENCES participants(username)
    ON UPDATE CASCADE ON DELETE RESTRICT;

ALTER TABLE "elsewhere" DROP CONSTRAINT
                                      "elsewhere_platform_participant_id_key";
ALTER TABLE "elsewhere" ADD CONSTRAINT "elsewhere_platform_participant_key"
    UNIQUE (platform, participant);


-- exchanges
ALTER TABLE exchanges RENAME COLUMN participant_id TO participant;

ALTER TABLE "exchanges" DROP CONSTRAINT "exchanges_participant_id_fkey";
ALTER TABLE "exchanges" ADD CONSTRAINT "exchanges_participant_fkey"
    FOREIGN KEY (participant) REFERENCES participants(username)
    ON UPDATE CASCADE ON DELETE RESTRICT;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/680

ALTER TABLE participants ADD COLUMN id bigserial NOT NULL UNIQUE;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/503

BEGIN;

    ALTER TABLE participants ADD COLUMN username_lower text
       NOT NULL DEFAULT '';

    UPDATE participants SET username_lower = lower(username);

END;

ALTER TABLE participants ADD UNIQUE (username_lower);
ALTER TABLE participants ALTER COLUMN username_lower DROP DEFAULT;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/449


BEGIN;

    -------------------
    -- participant type

    CREATE TYPE participant_type AS ENUM ( 'individual'
                                         , 'group'
                                         , 'open group'
                                          );

    CREATE TABLE log_participant_type
    ( id                serial                      PRIMARY KEY
    , ctime             timestamp with time zone    NOT NULL
    , mtime             timestamp with time zone    NOT NULL
                                                     DEFAULT CURRENT_TIMESTAMP
    , participant       text            NOT NULL REFERENCES participants
                                         ON UPDATE CASCADE ON DELETE RESTRICT
    , type              participant_type    NOT NULL
     );

    ALTER TABLE participants ADD COLUMN type participant_type
        NOT NULL DEFAULT 'individual';

    CREATE RULE log_participant_type
    AS ON UPDATE TO participants
              WHERE NEW.type <> OLD.type
                 DO
        INSERT INTO log_participant_type
                    (ctime, participant, type)
             VALUES ( COALESCE (( SELECT ctime
                                    FROM log_participant_type
                                   WHERE participant=OLD.username
                                   LIMIT 1
                                 ), CURRENT_TIMESTAMP)
                    , OLD.username
                    , NEW.type
                     );


    ------------------
    -- identifications

    CREATE TABLE identifications
    ( id                bigserial   PRIMARY KEY
    , ctime             timestamp with time zone    NOT NULL
    , mtime             timestamp with time zone    NOT NULL
                                                     DEFAULT CURRENT_TIMESTAMP
    , member            text        NOT NULL REFERENCES participants
                                     ON DELETE RESTRICT ON UPDATE CASCADE
    , "group"           text        NOT NULL REFERENCES participants
                                     ON DELETE RESTRICT ON UPDATE CASCADE
    , weight            int         NOT NULL DEFAULT 0
    , identified_by     text        NOT NULL REFERENCES participants
                                     ON DELETE RESTRICT ON UPDATE CASCADE
    , CONSTRAINT no_member_of_self CHECK (member != "group")
    , CONSTRAINT no_self_nomination CHECK (member != "identified_by")
    , CONSTRAINT no_stacking_the_deck CHECK ("group" != "identified_by")
     );


    CREATE VIEW current_identifications AS
    SELECT DISTINCT ON (member, "group", identified_by) i.*
               FROM identifications i
               JOIN participants p ON p.username = identified_by
              WHERE p.is_suspicious IS FALSE
           ORDER BY member
                  , "group"
                  , identified_by
                  , mtime DESC;

END;


-------------------------------------------------------------------------------

CREATE VIEW backed_tips AS
SELECT DISTINCT ON (tipper, tippee) t.*
           FROM tips t
           JOIN participants p ON p.username = tipper
          WHERE p.is_suspicious IS NOT TRUE
            AND p.last_bill_result=''
       ORDER BY tipper
              , tippee
              , mtime DESC;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/496

BEGIN;

    CREATE TABLE communities
    ( id            bigserial   PRIMARY KEY
    , ctime         timestamp with time zone    NOT NULL
    , mtime         timestamp with time zone    NOT NULL
                                                 DEFAULT CURRENT_TIMESTAMP
    , name          text        NOT NULL
    , slug          text        NOT NULL
    , participant   text        NOT NULL REFERENCES participants
                                 ON UPDATE CASCADE ON DELETE RESTRICT
    , is_member     boolean
     );

    CREATE VIEW current_communities AS
    SELECT DISTINCT ON (participant, slug) c.*
      FROM communities c
      JOIN participants p ON p.username = participant
     WHERE c.is_member AND p.is_suspicious IS FALSE
  ORDER BY participant
         , slug
         , mtime DESC;

    CREATE VIEW community_summary AS
    SELECT max(name) AS name -- gotta pick one, this is good enough for now
         , slug
         , count(participant) AS nmembers
      FROM current_communities
  GROUP BY slug
  ORDER BY nmembers DESC, slug;

END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/902

CREATE OR REPLACE VIEW current_communities AS
SELECT * FROM (
    SELECT DISTINCT ON (participant, slug) c.*
      FROM communities c
      JOIN participants p ON p.username = participant
     WHERE p.is_suspicious IS FALSE
  ORDER BY participant
         , slug
         , mtime DESC
) AS anon WHERE is_member;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/910

CREATE OR REPLACE VIEW current_communities AS
SELECT * FROM (
    SELECT DISTINCT ON (participant, slug) c.*
      FROM communities c
      JOIN participants p ON p.username = participant
     WHERE p.is_suspicious IS NOT TRUE
  ORDER BY participant
         , slug
         , mtime DESC
) AS anon WHERE is_member;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/910

ALTER TABLE paydays ADD COLUMN npachinko        bigint          DEFAULT 0;
ALTER TABLE paydays ADD COLUMN pachinko_volume  numeric(35,2)   DEFAULT 0.00;


-------------------------------------------------------------------------------
-- I want to see current tips as well as backed tips.

CREATE VIEW current_tips AS
  SELECT DISTINCT ON (tipper, tippee)
         t.*
       , p.last_bill_result AS tipper_last_bill_result
       , p.balance AS tipper_balance
    FROM tips t
    JOIN participants p ON p.username = tipper
   WHERE p.is_suspicious IS NOT TRUE
ORDER BY tipper
       , tippee
       , mtime DESC;

CREATE OR REPLACE VIEW backed_tips AS
SELECT * FROM current_tips
 WHERE tipper_last_bill_result='';


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/951

CREATE INDEX elsewhere_participant ON elsewhere(participant);


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/901

BEGIN;

    ALTER TABLE identifications DROP CONSTRAINT no_stacking_the_deck;


    -- Switch from is_suspicious IS FALSE to IS NOT TRUE. We're changing our
    -- criteria from "has moved money at all" to a rooted web of trust.

    CREATE OR REPLACE VIEW current_identifications AS
    SELECT DISTINCT ON (member, "group", identified_by) i.*
               FROM identifications i
               JOIN participants p ON p.username = identified_by
              WHERE p.is_suspicious IS NOT TRUE
           ORDER BY member
                  , "group"
                  , identified_by
                  , mtime DESC;

END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/7
-- https://github.com/gittip/www.gittip.com/issues/145

CREATE TABLE toots
( id                bigserial       PRIMARY KEY
, ctime             timestamp with time zone    NOT NULL
                                                 DEFAULT CURRENT_TIMESTAMP
, tooter            text            NOT NULL REFERENCES participants
                                     ON UPDATE CASCADE ON DELETE RESTRICT
, tootee            text            NOT NULL REFERENCES participants
                                     ON UPDATE CASCADE ON DELETE RESTRICT
, toot              text            NOT NULL
 );


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/1085

BEGIN;

    -- Create an api_keys table to track all api_keys a participant has
    -- created over time.
    CREATE TABLE api_keys
    ( id                serial                      PRIMARY KEY
    , ctime             timestamp with time zone    NOT NULL
    , mtime             timestamp with time zone    NOT NULL
                                                    DEFAULT CURRENT_TIMESTAMP
    , participant       text                        NOT NULL
                                                    REFERENCES participants
                                                    ON UPDATE CASCADE
                                                    ON DELETE RESTRICT
    , api_key        text                        NOT NULL UNIQUE
     );


    --
    ALTER TABLE participants ADD COLUMN api_key text DEFAULT NULL;


    -- Create a rule to log changes to participant.api_key into api_keys.
    CREATE RULE log_api_key_changes
    AS ON UPDATE TO participants
              WHERE (OLD.api_key IS NULL AND NOT NEW.api_key IS NULL)
                 OR (NEW.api_key IS NULL AND NOT OLD.api_key IS NULL)
                 OR NEW.api_key <> OLD.api_key
                 DO
        INSERT INTO api_keys
                    (ctime, participant, api_key)
             VALUES ( COALESCE (( SELECT ctime
                                    FROM api_keys
                                   WHERE participant=OLD.username
                                   LIMIT 1
                                 ), CURRENT_TIMESTAMP)
                    , OLD.username
                    , NEW.api_key
                     );

END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/1085

BEGIN;

    -- Whack identifications.
    DROP TABLE identifications CASCADE;


    -- Create a memberships table. Take is an int between 0 and 1000 inclusive,
    -- and is the tenths of a percent that the given member is taking from the
    -- given team. So if my take is 102 for gittip, that means I'm taking 10.2%
    -- of Gittip's budget. The application layer is responsible for ensuring
    -- that current takes sum to 1000 or less for a given team. Any shortfall
    -- is the take for the team itself.

    CREATE TABLE memberships
    ( id                serial                      PRIMARY KEY
    , ctime             timestamp with time zone    NOT NULL
    , mtime             timestamp with time zone    NOT NULL
                                                    DEFAULT CURRENT_TIMESTAMP
    , member            text                        NOT NULL
                                                    REFERENCES participants
                                                    ON UPDATE CASCADE
                                                    ON DELETE RESTRICT
    , team              text                        NOT NULL
                                                    REFERENCES participants
                                                    ON UPDATE CASCADE
                                                    ON DELETE RESTRICT
    , take              numeric(35,2)               NOT NULL DEFAULT 0.0
                                                    CONSTRAINT not_negative
                                                    CHECK (take >= 0)
    , CONSTRAINT no_team_recursion CHECK (team != member)
     );


    -- Create a current_memberships view.
    CREATE OR REPLACE VIEW current_memberships AS
    SELECT DISTINCT ON (member, team) m.*
               FROM memberships m
               JOIN participants p1 ON p1.username = member
               JOIN participants p2 ON p2.username = team
              WHERE p1.is_suspicious IS NOT TRUE
                AND p2.is_suspicious IS NOT TRUE
                AND take > 0
           ORDER BY member
                  , team
                  , mtime DESC;

END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/1100

ALTER TABLE memberships ADD COLUMN recorder text NOT NULL
    REFERENCES participants(username) ON UPDATE CASCADE ON DELETE RESTRICT;


-------------------------------------------------------------------------------
-- Recreate the current_memberships view. It had been including participants
-- who used to be members but weren't any longer.

CREATE OR REPLACE VIEW current_memberships AS
SELECT * FROM (

    SELECT DISTINCT ON (member, team) m.*
               FROM memberships m
               JOIN participants p1 ON p1.username = member
               JOIN participants p2 ON p2.username = team
              WHERE p1.is_suspicious IS NOT TRUE
                AND p2.is_suspicious IS NOT TRUE
           ORDER BY member
                  , team
                  , mtime DESC

) AS anon WHERE take > 0;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/1100

BEGIN;
    CREATE TYPE participant_type_ AS ENUM ( 'individual'
                                          , 'group'
                                           );

    ALTER TABLE participants ADD COLUMN type_ participant_type_
        NOT NULL DEFAULT 'individual';
    ALTER TABLE log_participant_type ADD COLUMN type_ participant_type_
        NOT NULL DEFAULT 'individual';

    UPDATE participants SET type_='group' WHERE type='group';
    UPDATE log_participant_type SET type_='group' WHERE type='group';

    DROP RULE log_participant_type ON participants;

    ALTER TABLE participants DROP COLUMN type;
    ALTER TABLE participants RENAME COLUMN type_ TO type;
    ALTER TABLE log_participant_type DROP COLUMN type;
    ALTER TABLE log_participant_type RENAME COLUMN type_ TO type;

    CREATE RULE log_participant_type
    AS ON UPDATE TO participants
              WHERE NEW.type <> OLD.type
                 DO
        INSERT INTO log_participant_type
                    (ctime, participant, type)
             VALUES ( COALESCE (( SELECT ctime
                                    FROM log_participant_type
                                   WHERE participant=OLD.username
                                   LIMIT 1
                                 ), CURRENT_TIMESTAMP)
                    , OLD.username
                    , NEW.type
                     );
END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/659

CREATE TABLE homepage_new_participants();
CREATE TABLE homepage_top_givers();
CREATE TABLE homepage_top_receivers();


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/1274

BEGIN;
    CREATE TYPE participant_number AS ENUM ('singular', 'plural');

    ALTER TABLE participants ADD COLUMN number participant_number
        NOT NULL DEFAULT 'singular';
    ALTER TABLE log_participant_type ADD COLUMN number participant_number
        NOT NULL DEFAULT 'singular';

    UPDATE participants SET number='plural' WHERE type='group';
    UPDATE log_participant_type SET number='plural' WHERE type='group';

    DROP RULE log_participant_type ON participants;

    ALTER TABLE participants DROP COLUMN type;
    ALTER TABLE log_participant_type DROP COLUMN type;

    ALTER TABLE log_participant_type RENAME TO log_participant_number;

    CREATE RULE log_participant_number
    AS ON UPDATE TO participants
              WHERE NEW.number <> OLD.number
                 DO
        INSERT INTO log_participant_number
                    (ctime, participant, number)
             VALUES ( COALESCE (( SELECT ctime
                                    FROM log_participant_number
                                   WHERE participant=OLD.username
                                   LIMIT 1
                                 ), CURRENT_TIMESTAMP)
                    , OLD.username
                    , NEW.number
                     );
END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/703

ALTER TABLE paydays
   ADD COLUMN nactive bigint DEFAULT 0;

UPDATE paydays SET nactive=(
    SELECT count(DISTINCT foo.*) FROM (
        SELECT tipper FROM transfers WHERE "timestamp" >= ts_start AND "timestamp" < ts_end
            UNION
        SELECT tippee FROM transfers WHERE "timestamp" >= ts_start AND "timestamp" < ts_end
        ) AS foo
);


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/1547

DROP TABLE homepage_new_participants;
DROP TABLE homepage_top_givers;
DROP TABLE homepage_top_receivers;
CREATE TABLE homepage_new_participants(username text, claimed_time timestamp with time zone);
CREATE TABLE homepage_top_givers(username text, anonymous boolean, amount numeric);
CREATE TABLE homepage_top_receivers(username text, claimed_time timestamp with time zone, amount numeric);


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/1582

ALTER TABLE participants ADD COLUMN paypal_email text DEFAULT NULL;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/1610

CREATE INDEX participants_claimed_time ON participants (claimed_time DESC)
  WHERE is_suspicious IS NOT TRUE
    AND claimed_time IS NOT null;

ALTER TABLE homepage_top_receivers ADD COLUMN gravatar_id text;
ALTER TABLE homepage_top_receivers ADD COLUMN twitter_pic text;

ALTER TABLE homepage_top_givers ADD COLUMN gravatar_id text;
ALTER TABLE homepage_top_givers ADD COLUMN twitter_pic text;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/1610

DROP TABLE homepage_new_participants;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/1683

BEGIN;
    ALTER TABLE participants RENAME COLUMN anonymous TO anonymous_giving;
    ALTER TABLE participants ADD COLUMN anonymous_receiving bool NOT NULL DEFAULT FALSE;
    ALTER TABLE homepage_top_receivers ADD COLUMN anonymous boolean;
END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/1164

BEGIN;
    CREATE TABLE bitcoin_addresses
    ( id                serial                      PRIMARY KEY
    , ctime             timestamp with time zone    NOT NULL
    , mtime             timestamp with time zone    NOT NULL
                                                     DEFAULT CURRENT_TIMESTAMP
    , participant       text            NOT NULL REFERENCES participants
                                         ON UPDATE CASCADE ON DELETE RESTRICT
    , bitcoin_address   text            NOT NULL
     );

    ALTER TABLE participants ADD COLUMN bitcoin_address text DEFAULT NULL;

    CREATE RULE bitcoin_addresses
    AS ON UPDATE TO participants
              WHERE NEW.bitcoin_address <> OLD.bitcoin_address
                 DO
        INSERT INTO bitcoin_addresses
                    (ctime, participant, bitcoin_address)
             VALUES ( COALESCE (( SELECT ctime
                                    FROM bitcoin_addresses
                                   WHERE participant=OLD.username
                                   LIMIT 1
                                 ), CURRENT_TIMESTAMP)
                    , OLD.username
                    , NEW.bitcoin_address
                     );

END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/1857

BEGIN;
    ALTER TABLE elsewhere ADD COLUMN access_token text DEFAULT NULL;
    ALTER TABLE elsewhere ADD COLUMN refresh_token text DEFAULT NULL;
    ALTER TABLE elsewhere ADD COLUMN expires timestamp with time zone DEFAULT NULL;
END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/2056

BEGIN;

    ALTER TABLE participants RENAME COLUMN balanced_account_uri TO balanced_customer_href;

END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/1369

BEGIN;


-- Add new columns

    -- Note: using "user_name" instead of "username" avoids having the same
    --       column name in the participants and elsewhere tables.
    ALTER TABLE elsewhere ADD COLUMN user_name text;
    ALTER TABLE elsewhere ADD COLUMN display_name text;
    ALTER TABLE elsewhere ADD COLUMN email text;
    ALTER TABLE elsewhere ADD COLUMN avatar_url text;
    ALTER TABLE participants ADD COLUMN avatar_url text;
    ALTER TABLE elsewhere ADD COLUMN is_team boolean NOT NULL DEFAULT FALSE;



-- Extract info

-- Note: The follow was run against production but doesn't need to be run in dev.
--
--    -- Extract user_name from user_info
--    UPDATE elsewhere SET user_name = user_id WHERE platform = 'bitbucket';
--    UPDATE elsewhere SET user_name = user_info->'display_name' WHERE platform = 'bountysource';
--    UPDATE elsewhere SET user_name = user_info->'login' WHERE platform = 'github';
--    UPDATE elsewhere SET user_name = user_info->'username' WHERE platform = 'openstreetmap';
--    UPDATE elsewhere SET user_name = user_info->'screen_name' WHERE platform = 'twitter';
--    UPDATE elsewhere SET user_name = user_info->'username' WHERE platform = 'venmo';
--
--    -- Extract display_name from user_info
--    UPDATE elsewhere SET display_name = user_info->'display_name' WHERE platform = 'bitbucket';
--    UPDATE elsewhere SET display_name = user_info->'name' WHERE platform = 'github';
--    UPDATE elsewhere SET display_name = user_info->'username' WHERE platform = 'openstreetmap';
--    UPDATE elsewhere SET display_name = user_info->'name' WHERE platform = 'twitter';
--    UPDATE elsewhere SET display_name = user_info->'display_name' WHERE platform = 'venmo';
--    UPDATE elsewhere SET display_name = NULL WHERE display_name = 'None';
--
--    -- Extract available email addresses
--    UPDATE elsewhere SET email = user_info->'email' WHERE user_info->'email' LIKE '%@%';
--
--    -- Extract available avatar URLs
--    UPDATE elsewhere SET avatar_url = concat('https://www.gravatar.com/avatar/',
--                                             user_info->'gravatar_id')
--                   WHERE platform = 'github'
--                     AND user_info->'gravatar_id' != ''
--                     AND user_info->'gravatar_id' != 'None';
--    UPDATE elsewhere SET avatar_url = concat('https://www.gravatar.com/avatar/',
--                                             md5(lower(trim(email))))
--                   WHERE email IS NOT NULL AND avatar_url IS NULL;
--    UPDATE elsewhere SET avatar_url = user_info->'avatar' WHERE platform = 'bitbucket';
--    UPDATE elsewhere SET avatar_url = user_info->'avatar_url'
--                   WHERE platform = 'bitbucket' AND avatar_url IS NULL;
--    UPDATE elsewhere SET avatar_url = substring(user_info->'links', $$u'avatar': {u'href': u'([^']+)$$)
--                   WHERE platform = 'bitbucket' AND avatar_url IS NULL;
--    UPDATE elsewhere SET avatar_url = user_info->'image_url' WHERE platform = 'bountysource';
--    UPDATE elsewhere SET avatar_url = user_info->'avatar_url' WHERE platform = 'github' AND avatar_url IS NULL;
--    UPDATE elsewhere SET avatar_url = user_info->'img_src' WHERE platform = 'openstreetmap';
--    UPDATE elsewhere SET avatar_url = replace(user_info->'profile_image_url_https', '_normal.', '.')
--                   WHERE platform = 'twitter';
--    UPDATE elsewhere SET avatar_url = user_info->'profile_picture_url' WHERE platform = 'venmo';
--    UPDATE elsewhere SET avatar_url = NULL WHERE avatar_url = 'None';
--    -- Propagate avatar_url to participants
--    UPDATE participants p
--       SET avatar_url = (
--               SELECT avatar_url
--                 FROM elsewhere
--                WHERE participant = p.username
--             ORDER BY platform = 'github' DESC,
--                      avatar_url LIKE '%gravatar.com%' DESC
--                LIMIT 1
--           );
--
--    -- Extract is_team from user_info
--    UPDATE elsewhere SET is_team = true WHERE platform = 'bitbucket' AND user_info->'is_team' = 'True';
--    UPDATE elsewhere SET is_team = true WHERE platform = 'github' AND lower(user_info->'type') = 'organization';



-- Drop old columns and add new ones

    -- Update user_name constraints
    ALTER TABLE elsewhere ALTER COLUMN user_name SET NOT NULL,
                          ALTER COLUMN user_name DROP DEFAULT;

    -- Replace user_info by a new column of type json (instead of hstore)
    ALTER TABLE elsewhere DROP COLUMN user_info,
                          ADD COLUMN extra_info json;
    DROP EXTENSION hstore;

    -- Simplify homepage_top_* tables
    ALTER TABLE homepage_top_givers DROP COLUMN gravatar_id,
                                    DROP COLUMN twitter_pic,
                                    ADD COLUMN avatar_url text;
    ALTER TABLE homepage_top_receivers DROP COLUMN claimed_time,
                                       DROP COLUMN gravatar_id,
                                       DROP COLUMN twitter_pic,
                                       ADD COLUMN avatar_url text;

    -- The following lets us cast queries to elsewhere_with_participant to get the
    -- participant data dereferenced and returned in a composite type along with
    -- the elsewhere data. Then we can register orm.Models in the application for
    -- both participant and elsewhere_with_participant, and when we cast queries
    -- elsewhere.*::elsewhere_with_participant, we'll get a hydrated Participant
    -- object at .participant. Woo-hoo!

    CREATE TYPE elsewhere_with_participant AS
    ( id            integer
    , platform      text
    , user_id       text
    , user_name     text
    , display_name  text
    , email         text
    , avatar_url    text
    , extra_info    json
    , is_locked     boolean
    , is_team       boolean
    , participant   participants
     ); -- If Postgres had type inheritance this would be even awesomer.

    CREATE OR REPLACE FUNCTION load_participant_for_elsewhere (elsewhere)
    RETURNS elsewhere_with_participant
    AS $$
        SELECT $1.id
             , $1.platform
             , $1.user_id
             , $1.user_name
             , $1.display_name
             , $1.email
             , $1.avatar_url
             , $1.extra_info
             , $1.is_locked
             , $1.is_team
             , participants.*::participants
          FROM participants
         WHERE participants.username = $1.participant
              ;
    $$ LANGUAGE SQL;

    CREATE CAST (elsewhere AS elsewhere_with_participant)
        WITH FUNCTION load_participant_for_elsewhere(elsewhere);

END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/2006

BEGIN;
    CREATE TABLE events
    ( id        serial      PRIMARY KEY
    , ts        timestamp   NOT NULL DEFAULT CURRENT_TIMESTAMP
    , type      text        NOT NULL
    , payload   json
     );

    CREATE INDEX events_ts ON events(ts ASC);
    CREATE INDEX events_type ON events(type);

    /* ran branch.py here, took forever :-/ */

    DROP RULE log_api_key_changes ON participants;
    DROP RULE log_goal_changes ON participants;
    DROP TABLE goals, api_keys;

END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/1675

BEGIN;
    ALTER TABLE participants ADD COLUMN paypal_fee_cap numeric(35,2);

    -- Update not needed in dev.
    -- UPDATE participants SET paypal_fee_cap=20 WHERE paypal_email IS NOT NULL;
END;


-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/2172

BEGIN;
    ALTER TABLE homepage_top_receivers ADD COLUMN statement text;
    ALTER TABLE homepage_top_receivers ADD COLUMN number text;

    ALTER TABLE homepage_top_givers ADD COLUMN statement text;
    ALTER TABLE homepage_top_givers ADD COLUMN number text;
END;
