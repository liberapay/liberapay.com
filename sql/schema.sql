-------------------------------------------------------------------------------
--                             million trillion trillion
--                             |         trillion trillion
--                             |         |               trillion
--                             |         |               |   billion
--                             |         |               |   |   million
--                             |         |               |   |   |   thousand
--                             |         |               |   |   |   |
-- numeric(35,2) maxes out at $999,999,999,999,999,999,999,999,999,999,999.00.


CREATE EXTENSION pg_trgm;

CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA public;
COMMENT ON EXTENSION pg_stat_statements IS 'track execution statistics of all SQL statements executed';

\i sql/enforce-utc.sql

\i sql/enumerate.sql


-- participants -- user accounts

CREATE TYPE participant_kind AS ENUM ('individual', 'organization', 'group');
CREATE TYPE participant_status AS ENUM ('stub', 'active', 'closed');

CREATE TABLE participants
( id                    bigserial               PRIMARY KEY
, username              text                    NOT NULL
, email                 text                    UNIQUE
, email_lang            text
, password              text
, password_mtime        timestamptz
, kind                  participant_kind
, status                participant_status      NOT NULL DEFAULT 'stub'
, is_admin              boolean                 NOT NULL DEFAULT FALSE
, session_token         text
, session_expires       timestamptz             DEFAULT (now() + INTERVAL '6 hours')
, join_time             timestamptz             DEFAULT NULL

, balance               numeric(35,2)           NOT NULL DEFAULT 0.0
, goal                  numeric(35,2)           DEFAULT NULL
, is_suspicious         boolean                 DEFAULT NULL
, balanced_customer_href  text                  DEFAULT NULL

, anonymous_giving      boolean                 NOT NULL DEFAULT FALSE
, anonymous_receiving   boolean                 NOT NULL DEFAULT FALSE
, is_searchable         bool                    NOT NULL DEFAULT TRUE

, avatar_url            text
, giving                numeric(35,2)           NOT NULL DEFAULT 0
, pledging              numeric(35,2)           NOT NULL DEFAULT 0
, receiving             numeric(35,2)           NOT NULL DEFAULT 0
, taking                numeric(35,2)           NOT NULL DEFAULT 0
, npatrons              integer                 NOT NULL DEFAULT 0

, email_notif_bits      int                     NOT NULL DEFAULT 2147483647
, pending_notifs        int                     NOT NULL DEFAULT 0 CHECK (pending_notifs >= 0)

, CONSTRAINT balance_chk CHECK (NOT (status <> 'active' AND balance <> 0))
, CONSTRAINT join_time_chk CHECK ((status='stub') = (join_time IS NULL))
, CONSTRAINT kind_chk CHECK ((status='stub') = (kind IS NULL))
, CONSTRAINT password_chk CHECK ((status='stub' OR kind='group') = (password IS NULL))
 );

CREATE UNIQUE INDEX ON participants (lower(username));

CREATE INDEX username_trgm_idx ON participants
    USING gist(lower(username) gist_trgm_ops)
    WHERE status = 'active';

CREATE INDEX participants_join_time_idx ON participants (join_time)
    WHERE join_time IS NOT NULL;

CREATE FUNCTION fill_username() RETURNS trigger AS $$
    BEGIN
        NEW.username = '~'||NEW.id::text;
        RETURN NEW;
    END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER fill_username BEFORE INSERT ON participants
    FOR EACH ROW WHEN (NEW.username IS NULL) EXECUTE PROCEDURE fill_username();


-- elsewhere -- social network accounts attached to participants

CREATE TABLE elsewhere
( id                    serial          PRIMARY KEY
, participant           bigint          NOT NULL REFERENCES participants
, platform              text            NOT NULL
, user_id               text            NOT NULL
, user_name             text
-- Note: we use "user_name" instead of "username" to avoid having the same
--       column name in the participants and elsewhere tables.
, display_name          text
, email                 text
, avatar_url            text
, is_team               boolean         NOT NULL DEFAULT FALSE
, extra_info            json
, token                 json
, connect_token         text
, connect_expires       timestamptz
, UNIQUE (platform, user_id)
, UNIQUE (participant, platform)
 );

\i sql/elsewhere_with_participant.sql

CREATE UNIQUE INDEX ON elsewhere (lower(user_name), platform);


-- tips -- all times a participant elects to tip another

CREATE TABLE tips
( id           serial           PRIMARY KEY
, ctime        timestamptz      NOT NULL
, mtime        timestamptz      NOT NULL DEFAULT CURRENT_TIMESTAMP
, tipper       bigint           NOT NULL REFERENCES participants
, tippee       bigint           NOT NULL REFERENCES participants
, amount       numeric(35,2)    NOT NULL CHECK (amount >= 0)
, is_funded    boolean          NOT NULL DEFAULT false
 );

CREATE INDEX tips_tipper_idx ON tips (tipper, mtime DESC);
CREATE INDEX tips_tippee_idx ON tips (tippee, mtime DESC);

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


-- transfers -- balance transfers from one user to another

CREATE TYPE transfer_context AS ENUM
    ('tip', 'take', 'final-gift', 'take-over');

CREATE TABLE transfers
( id          serial              PRIMARY KEY
, timestamp   timestamptz         NOT NULL DEFAULT CURRENT_TIMESTAMP
, tipper      bigint              NOT NULL REFERENCES participants
, tippee      bigint              NOT NULL REFERENCES participants
, amount      numeric(35,2)       NOT NULL CHECK (amount > 0)
, context     transfer_context    NOT NULL
 );

CREATE INDEX transfers_tipper_idx ON transfers (tipper);
CREATE INDEX transfers_tippee_idx ON transfers (tippee);


-- paydays -- payday events, stats about them

CREATE TABLE paydays
( id                    serial           PRIMARY KEY
, ts_start              timestamptz      NOT NULL DEFAULT CURRENT_TIMESTAMP
, ts_end                timestamptz      UNIQUE NOT NULL DEFAULT '1970-01-01T00:00:00+00'::timestamptz
, nparticipants         bigint           NOT NULL DEFAULT 0
, ntippers              bigint           NOT NULL DEFAULT 0
, ntips                 bigint           NOT NULL DEFAULT 0
, ntransfers            bigint           NOT NULL DEFAULT 0
, transfer_volume       numeric(35,2)    NOT NULL DEFAULT 0.00
, ncc_failing           bigint           NOT NULL DEFAULT 0
, ncc_missing           bigint           NOT NULL DEFAULT 0
, ncharges              bigint           NOT NULL DEFAULT 0
, charge_volume         numeric(35,2)    NOT NULL DEFAULT 0.00
, charge_fees_volume    numeric(35,2)    NOT NULL DEFAULT 0.00
, nachs                 bigint           NOT NULL DEFAULT 0
, ach_volume            numeric(35,2)    NOT NULL DEFAULT 0.00
, ach_fees_volume       numeric(35,2)    NOT NULL DEFAULT 0.00
, nach_failing          bigint           NOT NULL DEFAULT 0
, npachinko             bigint           NOT NULL DEFAULT 0
, pachinko_volume       numeric(35,2)    NOT NULL DEFAULT 0.00
, nactive               bigint           NOT NULL DEFAULT 0
, stage                 integer          DEFAULT 0
 );


-- exchange routes -- how money moves in and out of Liberapay

CREATE TYPE payment_net AS ENUM
    ('balanced-ba', 'balanced-cc', 'paypal', 'bitcoin');

CREATE TABLE exchange_routes
( id            serial         PRIMARY KEY
, participant   bigint         NOT NULL REFERENCES participants
, network       payment_net    NOT NULL
, address       text           NOT NULL CHECK (address <> '')
, error         text           NOT NULL
, fee_cap       numeric(35,2)
, UNIQUE (participant, network, address)
);

CREATE VIEW current_exchange_routes AS
    SELECT DISTINCT ON (participant, network) *
      FROM exchange_routes
  ORDER BY participant, network, id DESC;

CREATE CAST (current_exchange_routes AS exchange_routes) WITH INOUT;


-- exchanges -- when a participant moves cash between Liberapay and their bank

CREATE TYPE exchange_status AS ENUM ('pre', 'pending', 'failed', 'succeeded');

CREATE TABLE exchanges
( id                serial               PRIMARY KEY
, timestamp         timestamptz          NOT NULL DEFAULT CURRENT_TIMESTAMP
, amount            numeric(35,2)        NOT NULL
, fee               numeric(35,2)        NOT NULL
, participant       bigint               NOT NULL REFERENCES participants
, recorder          bigint               REFERENCES participants
, note              text
, status            exchange_status      NOT NULL
, route             bigint               REFERENCES exchange_routes
 );

CREATE INDEX exchanges_participant_idx ON exchanges (participant);


-- communities -- groups of participants

CREATE TABLE community_members
( slug          text           NOT NULL
, participant   bigint         NOT NULL REFERENCES participants
, ctime         timestamptz    NOT NULL DEFAULT CURRENT_TIMESTAMP
, mtime         timestamptz    NOT NULL DEFAULT CURRENT_TIMESTAMP
, name          text           NOT NULL
, is_member     boolean        NOT NULL
, UNIQUE (slug, participant)
);

CREATE TABLE communities
( slug text PRIMARY KEY
, name text UNIQUE NOT NULL
, nmembers int NOT NULL
, ctime timestamptz NOT NULL
, CHECK (nmembers > 0)
);

\i sql/upsert_community.sql

CREATE TRIGGER upsert_community
    BEFORE INSERT OR UPDATE OR DELETE ON community_members
    FOR EACH ROW
    EXECUTE PROCEDURE upsert_community();

CREATE INDEX community_trgm_idx ON communities
    USING gist(name gist_trgm_ops);


-- takes -- how members of a team share the money it receives

CREATE TABLE takes
( id                serial               PRIMARY KEY
, ctime             timestamptz          NOT NULL
, mtime             timestamptz          NOT NULL DEFAULT CURRENT_TIMESTAMP
, member            bigint               NOT NULL REFERENCES participants
, team              bigint               NOT NULL REFERENCES participants
, amount            numeric(35,2)        NOT NULL DEFAULT 0.0
, recorder          bigint               NOT NULL REFERENCES participants
, CONSTRAINT no_team_recursion CHECK (team <> member)
, CONSTRAINT not_negative CHECK ((amount >= (0)::numeric))
 );

CREATE VIEW current_takes AS
    SELECT * FROM (
         SELECT DISTINCT ON (member, team) t.*
           FROM takes t
           JOIN participants p1 ON p1.id = member
           JOIN participants p2 ON p2.id = team
          WHERE p1.is_suspicious IS NOT TRUE
            AND p2.is_suspicious IS NOT TRUE
       ORDER BY member
              , team
              , mtime DESC
    ) AS anon WHERE amount > 0;


-- log of participant events

CREATE TABLE events
( id           bigserial     PRIMARY KEY
, ts           timestamptz   NOT NULL DEFAULT CURRENT_TIMESTAMP
, participant  bigint        NOT NULL REFERENCES participants
, type         text          NOT NULL
, payload      json
, recorder     bigint        REFERENCES participants
 );

CREATE INDEX events_participant_idx ON events (participant, type);


-- email addresses

CREATE TABLE emails
( id                serial         PRIMARY KEY
, address           text           NOT NULL
, verified          boolean        CHECK (verified IS NOT FALSE)
, nonce             text
, added_time        timestamptz    NOT NULL DEFAULT CURRENT_TIMESTAMP
, verified_time     timestamptz
, participant       bigint         NOT NULL REFERENCES participants
, UNIQUE (address, verified)
    -- A verified email address can't be linked to multiple participants.
    -- However, an *un*verified address *can* be linked to multiple
    -- participants. We implement this by using NULL instead of FALSE for the
    -- unverified state, hence the check constraint on verified.
, UNIQUE (participant, address)
 );


-- profile statements

CREATE TABLE statements
( participant    bigint      NOT NULL REFERENCES participants
, lang           text        NOT NULL
, content        text        NOT NULL CHECK (content <> '')
, search_vector  tsvector
, search_conf    regconfig   NOT NULL
, UNIQUE (participant, lang)
);

CREATE INDEX statements_fts_idx ON statements USING gist(search_vector);

CREATE TRIGGER search_vector_update
    BEFORE INSERT OR UPDATE ON statements
    FOR EACH ROW EXECUTE PROCEDURE
    tsvector_update_trigger_column(search_vector, search_conf, content);


-- emails waiting to be sent

CREATE TABLE email_queue
( id            serial   PRIMARY KEY
, participant   bigint   NOT NULL REFERENCES participants
, spt_name      text     NOT NULL
, context       bytea    NOT NULL
);


-- web notifications waiting to be displayed

CREATE TABLE notification_queue
( id            serial   PRIMARY KEY
, participant   bigint   NOT NULL REFERENCES participants
, event         text     NOT NULL
, context       bytea    NOT NULL
);


-- cache of participant balances at specific times

CREATE TABLE balances_at
( participant  bigint         NOT NULL REFERENCES participants
, at           timestamptz    NOT NULL
, balance      numeric(35,2)  NOT NULL
, UNIQUE (participant, at)
);
