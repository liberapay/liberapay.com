-------------------------------------------------------------------------------
--                             million trillion trillion
--                             |         trillion trillion
--                             |         |               trillion
--                             |         |               |   billion
--                             |         |               |   |   million
--                             |         |               |   |   |   thousand
--                             |         |               |   |   |   |
-- numeric(35,2) maxes out at $999,999,999,999,999,999,999,999,999,999,999.00.


CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA public;
COMMENT ON EXTENSION pg_stat_statements IS 'track execution statistics of all SQL statements executed';


-- https://github.com/gratipay/gratipay.com/pull/1274
CREATE TYPE participant_number AS ENUM ('singular', 'plural');


-- https://github.com/gratipay/gratipay.com/pull/2303
CREATE TYPE email_address_with_confirmation AS
(
    address text,
    confirmed boolean
);


CREATE TABLE participants
( username              text                        PRIMARY KEY
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
, email_address         text                        UNIQUE
, email_lang            text
, is_searchable         bool                        NOT NULL DEFAULT TRUE
, CONSTRAINT team_not_anonymous CHECK (NOT (number='plural' AND anonymous_receiving))
 );

-- https://github.com/gratipay/gratipay.com/pull/1610
CREATE INDEX participants_claimed_time ON participants (claimed_time DESC)
  WHERE is_suspicious IS NOT TRUE
    AND claimed_time IS NOT null;


CREATE TABLE elsewhere
( id                    serial          PRIMARY KEY
, platform              text            NOT NULL
, user_id               text            NOT NULL
, participant           text            NOT NULL REFERENCES participants ON UPDATE CASCADE ON DELETE RESTRICT
, user_name             text
-- Note: using "user_name" instead of "username" avoids having the same
--       column name in the participants and elsewhere tables.
, display_name          text
, email                 text
, avatar_url            text
, is_team               boolean         NOT NULL DEFAULT FALSE
, extra_info            json
, token                 json
, UNIQUE (platform, user_id)
, UNIQUE (platform, participant)
 );

-- https://github.com/gratipay/gratipay.com/issues/951
CREATE INDEX elsewhere_participant ON elsewhere(participant);


-- tips -- all times a participant elects to tip another
CREATE TABLE tips
( id                    serial                      PRIMARY KEY
, ctime                 timestamp with time zone    NOT NULL
, mtime                 timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, tipper                text                        NOT NULL REFERENCES participants ON UPDATE CASCADE ON DELETE RESTRICT
, tippee                text                        NOT NULL REFERENCES participants ON UPDATE CASCADE ON DELETE RESTRICT
, amount                numeric(35,2)               NOT NULL
, is_funded             boolean                     NOT NULL DEFAULT false
 );

CREATE INDEX tips_all ON tips USING btree (tipper, tippee, mtime DESC);

CREATE VIEW current_tips AS
    SELECT DISTINCT ON (tipper, tippee) *
      FROM tips
  ORDER BY tipper, tippee, mtime DESC;

-- Allow updating is_funded via the current_tips view for convenience
CREATE FUNCTION update_tip() RETURNS trigger AS $$
    BEGIN
        UPDATE tips
           SET is_funded = NEW.is_funded
         WHERE id = NEW.id;
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_current_tip INSTEAD OF UPDATE ON current_tips
    FOR EACH ROW EXECUTE PROCEDURE update_tip();


-- https://github.com/gratipay/gratipay.com/pull/2501
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

-- https://github.com/gratipay/gratipay.com/pull/2723
ALTER TABLE transfers ADD CONSTRAINT positive CHECK (amount > 0) NOT VALID;

-- https://github.com/gratipay/gratipay.com/pull/3040
CREATE INDEX transfers_timestamp_idx ON transfers (timestamp);
CREATE INDEX transfers_tipper_idx ON transfers (tipper);
CREATE INDEX transfers_tippee_idx ON transfers (tippee);


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


-- https://github.com/gratipay/gratipay.com/pull/2579
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


-- https://github.com/gratipay/gratipay.com/issues/406
CREATE TABLE absorptions
( id                    serial                      PRIMARY KEY
, timestamp             timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, absorbed_was          text                        NOT NULL -- Not a foreign key!
, absorbed_by           text                        NOT NULL REFERENCES participants ON DELETE RESTRICT ON UPDATE CASCADE
, archived_as           text                        NOT NULL REFERENCES participants ON DELETE RESTRICT ON UPDATE RESTRICT
-- Here we actually want ON UPDATE RESTRICT as a sanity check:
-- noone should be changing usernames of absorbed accounts.
 );


-- https://github.com/gratipay/gratipay.com/pull/2701
CREATE TABLE community_members
( slug          text           NOT NULL
, participant   bigint         NOT NULL REFERENCES participants(id)
, ctime         timestamptz    NOT NULL
, mtime         timestamptz    NOT NULL DEFAULT CURRENT_TIMESTAMP
, name          text           NOT NULL
, is_member     boolean        NOT NULL
);

CREATE INDEX community_members_idx
    ON community_members (slug, participant, mtime DESC);

CREATE TABLE communities
( slug text PRIMARY KEY
, name text UNIQUE NOT NULL
, nmembers int NOT NULL
, ctime timestamptz NOT NULL
, CHECK (nmembers >= 0)
);

CREATE FUNCTION upsert_community() RETURNS trigger AS $$
    DECLARE
        is_member boolean;
    BEGIN
        IF (SELECT is_suspicious FROM participants WHERE id = NEW.participant) THEN
            RETURN NULL;
        END IF;
        is_member := (
            SELECT cur.is_member
              FROM community_members cur
             WHERE slug = NEW.slug
               AND participant = NEW.participant
          ORDER BY mtime DESC
             LIMIT 1
        );
        IF (is_member IS NULL AND NEW.is_member IS false OR NEW.is_member = is_member) THEN
            RETURN NULL;
        END IF;
        LOOP
            UPDATE communities
               SET nmembers = nmembers + (CASE WHEN NEW.is_member THEN 1 ELSE -1 END)
             WHERE slug = NEW.slug;
            EXIT WHEN FOUND;
            BEGIN
                INSERT INTO communities
                     VALUES (NEW.slug, NEW.name, 1, NEW.ctime);
            EXCEPTION
                WHEN unique_violation THEN
                    IF (CONSTRAINT_NAME = 'communities_slug_pkey') THEN
                        CONTINUE; -- Try again
                    ELSE
                        RAISE;
                    END IF;
            END;
            EXIT;
        END LOOP;
        RETURN NEW;
    END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER upsert_community BEFORE INSERT ON community_members
    FOR EACH ROW
    EXECUTE PROCEDURE upsert_community();

CREATE VIEW current_community_members AS
    SELECT DISTINCT ON (participant, slug) c.*
      FROM community_members c
  ORDER BY participant, slug, mtime DESC;


-- https://github.com/gratipay/gratipay.com/issues/1100
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


-- https://github.com/gratipay/gratipay.com/pull/1369
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
, is_team       boolean
, token         json
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
         , $1.is_team
         , $1.token
         , participants.*::participants
      FROM participants
     WHERE participants.username = $1.participant
          ;
$$ LANGUAGE SQL;

CREATE CAST (elsewhere AS elsewhere_with_participant)
    WITH FUNCTION load_participant_for_elsewhere(elsewhere);


-- https://github.com/gratipay/gratipay.com/pull/2006
CREATE TABLE events
( id        serial      PRIMARY KEY
, ts        timestamp   NOT NULL DEFAULT CURRENT_TIMESTAMP
, type      text        NOT NULL
, payload   json
 );

CREATE INDEX events_ts ON events(ts ASC);
CREATE INDEX events_type ON events(type);


-- https://github.com/gratipay/gratipay.com/pulls/2752
CREATE TABLE emails
( id                    serial                      PRIMARY KEY
, address               text                        NOT NULL
, verified              boolean                     DEFAULT NULL
                                                      CONSTRAINT verified_cant_be_false
                                                        -- Only use TRUE and NULL, so that the
                                                        -- unique constraint below functions
                                                        -- properly.
                                                        CHECK (verified IS NOT FALSE)
, nonce                 text
, verification_start    timestamp with time zone    NOT NULL
                                                      DEFAULT CURRENT_TIMESTAMP
, verification_end      timestamp with time zone
, participant           text                        NOT NULL
                                                      REFERENCES participants
                                                      ON UPDATE CASCADE
                                                      ON DELETE RESTRICT

, UNIQUE (address, verified) -- A verified email address can't be linked to multiple
                             -- participants. However, an *un*verified address *can*
                             -- be linked to multiple participants. We implement this
                             -- by using NULL instead of FALSE for the unverified
                             -- state, hence the check constraint on verified.
, UNIQUE (participant, address)
 );


-- https://github.com/gratipay/gratipay.com/pull/3010
CREATE TABLE statements
( participant  bigint  NOT NULL REFERENCES participants(id)
, lang         text    NOT NULL
, content      text    NOT NULL CHECK (content <> '')
, UNIQUE (participant, lang)
);

CREATE FUNCTION enumerate(anyarray) RETURNS TABLE (rank bigint, value anyelement) AS $$
    SELECT row_number() over() as rank, value FROM unnest($1) value;
$$ LANGUAGE sql STABLE;


-- Index user and community names

CREATE EXTENSION pg_trgm;

CREATE INDEX username_trgm_idx ON participants
    USING gist(username_lower gist_trgm_ops)
    WHERE claimed_time IS NOT NULL AND NOT is_closed;

CREATE INDEX community_trgm_idx ON communities
    USING gist(name gist_trgm_ops);

-- Index statements

ALTER TABLE statements ADD COLUMN search_vector tsvector;
ALTER TABLE statements ADD COLUMN search_conf regconfig NOT NULL;

CREATE INDEX statements_fts_idx ON statements USING gist(search_vector);

CREATE TRIGGER search_vector_update
    BEFORE INSERT OR UPDATE ON statements
    FOR EACH ROW EXECUTE PROCEDURE
    tsvector_update_trigger_column(search_vector, search_conf, content);
