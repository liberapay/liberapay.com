-------------------------------------------------------------------------------
--                             million trillion trillion
--                             |         trillion trillion
--                             |         |               trillion
--                             |         |               |   billion
--                             |         |               |   |   million
--                             |         |               |   |   |   thousand
--                             |         |               |   |   |   |
-- numeric(35,2) maxes out at $999,999,999,999,999,999,999,999,999,999,999.00.


-- https://github.com/gratipay/www.gratipay.com/pull/1274
CREATE TYPE participant_number AS ENUM ('singular', 'plural');


-- https://github.com/gratipay/www.gratipay.com/pull/2305
CREATE TYPE email_address_with_confirmation AS
(
    address text,
    confirmed boolean
);


CREATE TABLE participants
( username              text                        PRIMARY KEY
, statement             text                        NOT NULL DEFAULT ''
, last_bill_result      text                        DEFAULT NULL
, session_token         text                        UNIQUE DEFAULT NULL
, session_expires       timestamp with time zone    DEFAULT (now() + INTERVAL '6 hours')
, ctime                 timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, claimed_time          timestamp with time zone    DEFAULT NULL
, is_admin              boolean                     NOT NULL DEFAULT FALSE
, balance               numeric(35,2)               NOT NULL DEFAULT 0.0
, anonymous_giving      boolean                     NOT NULL DEFAULT FALSE
, goal                  numeric(35,2)               DEFAULT NULL
, balanced_customer_href  text                      DEFAULT NULL
, last_ach_result       text                        DEFAULT NULL
, is_suspicious         boolean                     DEFAULT NULL
, id                    bigserial                   NOT NULL UNIQUE
, username_lower        text                        NOT NULL UNIQUE
, api_key               text                        UNIQUE DEFAULT NULL
, number                participant_number          NOT NULL DEFAULT 'singular'
, paypal_email          text                        DEFAULT NULL
, anonymous_receiving   boolean                     NOT NULL DEFAULT FALSE
, bitcoin_address       text                        DEFAULT NULL
, avatar_url            text
, paypal_fee_cap        numeric(35,2)
, email                 email_address_with_confirmation
, is_closed             boolean                     NOT NULL DEFAULT FALSE
, giving                numeric(35,2)               NOT NULL DEFAULT 0
, pledging              numeric(35,2)               NOT NULL DEFAULT 0
, receiving             numeric(35,2)               NOT NULL DEFAULT 0
, taking                numeric(35,2)               NOT NULL DEFAULT 0
, npatrons              integer                     NOT NULL DEFAULT 0
, is_free_rider         boolean                     DEFAULT NULL
 );

-- https://github.com/gratipay/www.gratipay.com/pull/1610
CREATE INDEX participants_claimed_time ON participants (claimed_time DESC)
  WHERE is_suspicious IS NOT TRUE
    AND claimed_time IS NOT null;


CREATE TABLE elsewhere
( id                    serial          PRIMARY KEY
, platform              text            NOT NULL
, user_id               text            NOT NULL
, participant           text            NOT NULL REFERENCES participants ON UPDATE CASCADE ON DELETE RESTRICT
, is_locked             boolean         NOT NULL DEFAULT FALSE
, access_token          text            DEFAULT NULL
, refresh_token         text            DEFAULT NULL
, expires               timestamptz     DEFAULT NULL
, user_name             text
-- Note: using "user_name" instead of "username" avoids having the same
--       column name in the participants and elsewhere tables.
, display_name          text
, email                 text
, avatar_url            text
, is_team               boolean         NOT NULL DEFAULT FALSE
, extra_info            json
, UNIQUE (platform, user_id)
, UNIQUE (platform, participant)
 );

-- https://github.com/gratipay/www.gratipay.com/issues/951
CREATE INDEX elsewhere_participant ON elsewhere(participant);


-- tips -- all times a participant elects to tip another
CREATE TABLE tips
( id                    serial                      PRIMARY KEY
, ctime                 timestamp with time zone    NOT NULL
, mtime                 timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, tipper                text                        NOT NULL REFERENCES participants ON UPDATE CASCADE ON DELETE RESTRICT
, tippee                text                        NOT NULL REFERENCES participants ON UPDATE CASCADE ON DELETE RESTRICT
, amount                numeric(35,2)               NOT NULL
 );

CREATE INDEX tips_all ON tips USING btree (tipper, tippee, mtime DESC);

CREATE VIEW current_tips AS
    SELECT DISTINCT ON (tipper, tippee) *
      FROM tips
  ORDER BY tipper, tippee, mtime DESC;


-- https://github.com/gratipay/www.gratipay.com/pull/2501
CREATE TYPE context_type AS ENUM
    ('tip', 'take', 'final-gift', 'take-over', 'one-off');


-- transfers -- balance transfers from one user to another
CREATE TABLE transfers
( id                    serial                      PRIMARY KEY
, timestamp             timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, tipper                text                        NOT NULL REFERENCES participants ON UPDATE CASCADE ON DELETE RESTRICT
, tippee                text                        NOT NULL REFERENCES participants ON UPDATE CASCADE ON DELETE RESTRICT
, amount                numeric(35,2)               NOT NULL
, context               context_type                NOT NULL
 );


-- paydays -- payday events, stats about them
CREATE TABLE paydays
( id                    serial                      PRIMARY KEY
, ts_start              timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, ts_end                timestamp with time zone    UNIQUE NOT NULL DEFAULT '1970-01-01T00:00:00+00'::timestamptz
, nparticipants         bigint                      NOT NULL DEFAULT 0
, ntippers              bigint                      NOT NULL DEFAULT 0
, ntips                 bigint                      NOT NULL DEFAULT 0
, ntransfers            bigint                      NOT NULL DEFAULT 0
, transfer_volume       numeric(35,2)               NOT NULL DEFAULT 0.00
, ncc_failing           bigint                      NOT NULL DEFAULT 0
, ncc_missing           bigint                      NOT NULL DEFAULT 0
, ncharges              bigint                      NOT NULL DEFAULT 0
, charge_volume         numeric(35,2)               NOT NULL DEFAULT 0.00
, charge_fees_volume    numeric(35,2)               NOT NULL DEFAULT 0.00
, nachs                 bigint                      NOT NULL DEFAULT 0
, ach_volume            numeric(35,2)               NOT NULL DEFAULT 0.00
, ach_fees_volume       numeric(35,2)               NOT NULL DEFAULT 0.00
, nach_failing          bigint                      NOT NULL DEFAULT 0
, npachinko             bigint                      NOT NULL DEFAULT 0
, pachinko_volume       numeric(35,2)               NOT NULL DEFAULT 0.00
, nactive               bigint                      NOT NULL DEFAULT 0
, stage                 integer                     DEFAULT 0
 );


-- https://github.com/gratipay/www.gratipay.com/pull/2579
CREATE TYPE exchange_status AS ENUM ('pre', 'pending', 'failed', 'succeeded');


-- exchanges -- when a participant moves cash between Gratipay and their bank
CREATE TABLE exchanges
( id                    serial                      PRIMARY KEY
, timestamp             timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, amount                numeric(35,2)               NOT NULL
, fee                   numeric(35,2)               NOT NULL
, participant           text                        NOT NULL REFERENCES participants ON UPDATE CASCADE ON DELETE RESTRICT
, recorder              text                        DEFAULT NULL REFERENCES participants ON UPDATE CASCADE ON DELETE RESTRICT
, note                  text                        DEFAULT NULL
, status                exchange_status
 );


-- https://github.com/gratipay/www.gratipay.com/issues/406
CREATE TABLE absorptions
( id                    serial                      PRIMARY KEY
, timestamp             timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, absorbed_was          text                        NOT NULL -- Not a foreign key!
, absorbed_by           text                        NOT NULL REFERENCES participants ON DELETE RESTRICT ON UPDATE CASCADE
, archived_as           text                        NOT NULL REFERENCES participants ON DELETE RESTRICT ON UPDATE RESTRICT
-- Here we actually want ON UPDATE RESTRICT as a sanity check:
-- noone should be changing usernames of absorbed accounts.
 );


-- https://github.com/gratipay/www.gratipay.com/issues/545
-- https://github.com/gratipay/www.gratipay.com/issues/778
CREATE VIEW goal_summary AS
  SELECT tippee as id
       , goal
       , CASE goal WHEN 0 THEN 0 ELSE (amount / goal) * 100 END AS percentage
       , statement
       , sum(amount) as amount
    FROM ( SELECT DISTINCT ON (tipper, tippee) tippee, amount
                         FROM tips
                         JOIN participants p ON p.username = tipper
                         JOIN participants p2 ON p2.username = tippee
                        WHERE p.last_bill_result = ''
                          AND p2.claimed_time IS NOT NULL
                     ORDER BY tipper, tippee, mtime DESC
          ) AS tips_agg
    JOIN participants p3 ON p3.username = tips_agg.tippee
   WHERE goal > 0
GROUP BY tippee, goal, percentage, statement;


-- https://github.com/gratipay/www.gratipay.com/issues/496
CREATE TABLE communities
( id            bigserial                   PRIMARY KEY
, ctime         timestamp with time zone    NOT NULL
, mtime         timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, name          text                        NOT NULL
, slug          text                        NOT NULL
, participant   text                        NOT NULL
    REFERENCES participants ON UPDATE CASCADE ON DELETE RESTRICT
, is_member     boolean
 );

-- https://github.com/gratipay/www.gratipay.com/pull/2430
CREATE INDEX ON communities (slug);

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

CREATE VIEW community_summary AS
    SELECT max(name) AS name -- gotta pick one, this is good enough for now
         , slug
         , count(participant) AS nmembers
      FROM current_communities
  GROUP BY slug
  ORDER BY nmembers DESC, slug;


-- https://github.com/gratipay/www.gratipay.com/issues/1085
CREATE TABLE takes
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
, amount            numeric(35,2)               NOT NULL DEFAULT 0.0
, recorder          text                        NOT NULL
                                                REFERENCES participants
                                                ON UPDATE CASCADE
                                                ON DELETE RESTRICT
, CONSTRAINT no_team_recursion CHECK (team != member)
, CONSTRAINT not_negative CHECK ((amount >= (0)::numeric))
 );

CREATE VIEW current_takes AS
    SELECT * FROM (
         SELECT DISTINCT ON (member, team) t.*
           FROM takes t
           JOIN participants p1 ON p1.username = member
           JOIN participants p2 ON p2.username = team
          WHERE p1.is_suspicious IS NOT TRUE
            AND p2.is_suspicious IS NOT TRUE
       ORDER BY member
              , team
              , mtime DESC
    ) AS anon WHERE amount > 0;


-- https://github.com/gratipay/www.gratipay.com/pull/1369
-- The following lets us cast queries to elsewhere_with_participant to get the
-- participant data dereferenced and returned in a composite type along with
-- the elsewhere data.
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


-- https://github.com/gratipay/www.gratipay.com/pull/2006
CREATE TABLE events
( id        serial      PRIMARY KEY
, ts        timestamp   NOT NULL DEFAULT CURRENT_TIMESTAMP
, type      text        NOT NULL
, payload   json
 );

CREATE INDEX events_ts ON events(ts ASC);
CREATE INDEX events_type ON events(type);


-- https://github.com/gratipay/www.gratipay.com/issues/1417
CREATE INDEX transfers_tipper_tippee_timestamp_idx
  ON transfers
  USING btree
  (tipper, tippee, timestamp DESC);


------------------------------------------------------------------------------
-- https://github.com/gratipay/www.gratipay.com/pull/2682

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
