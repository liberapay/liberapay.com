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

-- migration #15
ALTER TABLE transfers ADD COLUMN error text;

-- migration #16
ALTER TABLE participants ADD COLUMN is_suspended boolean;

-- migration #17
ALTER TYPE transfer_context ADD VALUE 'refund';

-- migration #18
ALTER TABLE transfers ADD COLUMN refund_ref bigint REFERENCES transfers;
ALTER TABLE exchanges ADD COLUMN refund_ref bigint REFERENCES exchanges;

-- migration #19
ALTER TABLE participants DROP CONSTRAINT password_chk;

-- migration #20
ALTER TABLE transfers
    DROP CONSTRAINT team_chk,
    ADD CONSTRAINT team_chk CHECK (NOT (context='take' AND team IS NULL));

-- migration #21
CREATE TYPE donation_period AS ENUM ('weekly', 'monthly', 'yearly');
ALTER TABLE tips
    ADD COLUMN period donation_period,
    ADD COLUMN periodic_amount numeric(35,2);
UPDATE tips SET period = 'weekly', periodic_amount = amount;
ALTER TABLE tips
    ALTER COLUMN period SET NOT NULL,
    ALTER COLUMN periodic_amount SET NOT NULL;
CREATE OR REPLACE VIEW current_tips AS
    SELECT DISTINCT ON (tipper, tippee) *
      FROM tips
  ORDER BY tipper, tippee, mtime DESC;

-- migration #22
DELETE FROM notification_queue WHERE event IN ('income', 'low_balance');

-- migration #23
INSERT INTO app_conf (key, value) VALUES ('csp_extra', '""'::jsonb);

-- migration #24
DELETE FROM app_conf WHERE key in ('compress_assets', 'csp_extra');

-- migration #25
DROP VIEW sponsors;
ALTER TABLE participants
    ALTER COLUMN profile_noindex DROP DEFAULT,
    ALTER COLUMN profile_noindex SET DATA TYPE int USING (profile_noindex::int | 2),
    ALTER COLUMN profile_noindex SET DEFAULT 2;
ALTER TABLE participants
    ALTER COLUMN hide_from_lists DROP DEFAULT,
    ALTER COLUMN hide_from_lists SET DATA TYPE int USING (hide_from_lists::int),
    ALTER COLUMN hide_from_lists SET DEFAULT 0;
ALTER TABLE participants
    ALTER COLUMN hide_from_search DROP DEFAULT,
    ALTER COLUMN hide_from_search SET DATA TYPE int USING (hide_from_search::int),
    ALTER COLUMN hide_from_search SET DEFAULT 0;
UPDATE participants p
   SET hide_from_lists = c.is_hidden::int
  FROM communities c
 WHERE c.participant = p.id;
ALTER TABLE communities DROP COLUMN is_hidden;
CREATE OR REPLACE VIEW sponsors AS
    SELECT *
      FROM participants p
     WHERE status = 'active'
       AND kind = 'organization'
       AND giving > receiving
       AND giving >= 10
       AND hide_from_lists = 0
       AND profile_noindex = 0
    ;
UPDATE participants SET profile_nofollow = true;

-- migration #26
DROP TYPE community_with_participant CASCADE;
DROP TYPE elsewhere_with_participant CASCADE;
CREATE TYPE community_with_participant AS
( c communities
, p participants
);
CREATE FUNCTION load_participant_for_community (communities)
RETURNS community_with_participant
AS $$
    SELECT $1, p
      FROM participants p
     WHERE p.id = $1.participant;
$$ LANGUAGE SQL;
CREATE CAST (communities AS community_with_participant)
    WITH FUNCTION load_participant_for_community(communities);
CREATE TYPE elsewhere_with_participant AS
( e elsewhere
, p participants
);
CREATE FUNCTION load_participant_for_elsewhere (elsewhere)
RETURNS elsewhere_with_participant
AS $$
    SELECT $1, p
      FROM participants p
     WHERE p.id = $1.participant;
$$ LANGUAGE SQL;
CREATE CAST (elsewhere AS elsewhere_with_participant)
    WITH FUNCTION load_participant_for_elsewhere(elsewhere);

-- migration #27
ALTER TABLE paydays
    ADD COLUMN transfer_volume_refunded numeric(35,2),
    ADD COLUMN week_deposits_refunded numeric(35,2),
    ADD COLUMN week_withdrawals_refunded numeric(35,2);

-- migration #28
INSERT INTO app_conf (key, value) VALUES ('socket_timeout', '10.0'::jsonb);

-- migration #29
CREATE TABLE newsletters
( id              bigserial     PRIMARY KEY
, ctime           timestamptz   NOT NULL DEFAULT CURRENT_TIMESTAMP
, sender          bigint        NOT NULL REFERENCES participants
);
CREATE TABLE newsletter_texts
( id              bigserial     PRIMARY KEY
, newsletter      bigint        NOT NULL REFERENCES newsletters
, lang            text          NOT NULL
, subject         text          NOT NULL CHECK (subject <> '')
, body            text          NOT NULL CHECK (body <> '')
, ctime           timestamptz   NOT NULL DEFAULT CURRENT_TIMESTAMP
, scheduled_for   timestamptz
, sent_at         timestamptz
, sent_count      int
, UNIQUE (newsletter, lang)
);
CREATE INDEX newsletter_texts_not_sent_idx
          ON newsletter_texts (scheduled_for ASC)
       WHERE sent_at IS NULL AND scheduled_for IS NOT NULL;
CREATE TABLE subscriptions
( id            bigserial      PRIMARY KEY
, publisher     bigint         NOT NULL REFERENCES participants
, subscriber    bigint         NOT NULL REFERENCES participants
, ctime         timestamptz    NOT NULL DEFAULT CURRENT_TIMESTAMP
, mtime         timestamptz    NOT NULL DEFAULT CURRENT_TIMESTAMP
, is_on         boolean        NOT NULL
, token         text
, UNIQUE (publisher, subscriber)
);
LOCK TABLE community_subscriptions IN EXCLUSIVE MODE;
INSERT INTO subscriptions (publisher, subscriber, ctime, mtime, is_on)
     SELECT c.participant, cs.participant, cs.ctime, cs.mtime, cs.is_on
       FROM community_subscriptions cs
       JOIN communities c ON c.id = cs.community
   ORDER BY cs.ctime ASC;
DROP TABLE community_subscriptions;
DROP FUNCTION IF EXISTS update_community_nsubscribers();
ALTER TABLE participants ADD COLUMN nsubscribers int NOT NULL DEFAULT 0;
LOCK TABLE communities IN EXCLUSIVE MODE;
UPDATE participants p
   SET nsubscribers = c.nsubscribers
  FROM communities c
 WHERE c.participant = p.id
   AND c.nsubscribers <> p.nsubscribers;
ALTER TABLE communities DROP COLUMN nsubscribers;
CREATE OR REPLACE FUNCTION update_community_nmembers() RETURNS trigger AS $$
    DECLARE
        old_is_on boolean = (CASE WHEN TG_OP = 'INSERT' THEN FALSE ELSE OLD.is_on END);
        new_is_on boolean = (CASE WHEN TG_OP = 'DELETE' THEN FALSE ELSE NEW.is_on END);
        delta int = CASE WHEN new_is_on THEN 1 ELSE -1 END;
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        IF (new_is_on = old_is_on) THEN
            RETURN (CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE rec END);
        END IF;
        UPDATE communities
           SET nmembers = nmembers + delta
         WHERE id = rec.community;
        RETURN rec;
    END;
$$ LANGUAGE plpgsql;
CREATE OR REPLACE FUNCTION update_nsubscribers() RETURNS trigger AS $$
    DECLARE
        old_is_on boolean = (CASE WHEN TG_OP = 'INSERT' THEN FALSE ELSE OLD.is_on END);
        new_is_on boolean = (CASE WHEN TG_OP = 'DELETE' THEN FALSE ELSE NEW.is_on END);
        delta int = CASE WHEN new_is_on THEN 1 ELSE -1 END;
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        IF (new_is_on = old_is_on) THEN
            RETURN (CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE rec END);
        END IF;
        UPDATE participants
           SET nsubscribers = nsubscribers + delta
         WHERE id = rec.publisher;
        RETURN rec;
    END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER update_nsubscribers
    BEFORE INSERT OR UPDATE OR DELETE ON subscriptions
    FOR EACH ROW
    EXECUTE PROCEDURE update_nsubscribers();

-- migration #30
ALTER TYPE transfer_context ADD VALUE 'expense';

-- migration #31
CREATE TYPE invoice_nature AS ENUM ('expense');
CREATE TYPE invoice_status AS ENUM
    ('pre', 'canceled', 'new', 'retracted', 'accepted', 'paid', 'rejected');
CREATE TABLE invoices
( id            serial            PRIMARY KEY
, ctime         timestamptz       NOT NULL DEFAULT CURRENT_TIMESTAMP
, sender        bigint            NOT NULL REFERENCES participants
, addressee     bigint            NOT NULL REFERENCES participants
, nature        invoice_nature    NOT NULL
, amount        numeric(35,2)     NOT NULL CHECK (amount > 0)
, description   text              NOT NULL
, details       text
, documents     jsonb             NOT NULL
, status        invoice_status    NOT NULL
);
CREATE TABLE invoice_events
( id            serial            PRIMARY KEY
, invoice       int               NOT NULL REFERENCES invoices
, participant   bigint            NOT NULL REFERENCES participants
, ts            timestamptz       NOT NULL DEFAULT CURRENT_TIMESTAMP
, status        invoice_status    NOT NULL
, message       text
);
ALTER TABLE participants ADD COLUMN allow_invoices boolean;
ALTER TABLE transfers
    ADD COLUMN invoice int REFERENCES invoices,
    ADD CONSTRAINT expense_chk CHECK (NOT (context='expense' AND invoice IS NULL));
INSERT INTO app_conf VALUES
    ('s3_endpoint', '""'::jsonb),
    ('s3_public_access_key', '""'::jsonb),
    ('s3_secret_key', '""'::jsonb),
    ('s3_region', '"eu-west-1"'::jsonb);

-- migration #32
ALTER TABLE cash_bundles
    ADD COLUMN withdrawal int REFERENCES exchanges,
    ALTER COLUMN owner DROP NOT NULL;
INSERT INTO cash_bundles
            (owner, origin, amount, ts)
     SELECT NULL, e2e.origin, e2e.amount
          , (SELECT e.timestamp FROM exchanges e WHERE e.id = e2e.origin)
       FROM e2e_transfers e2e;
DROP TABLE e2e_transfers;

-- migration #33
ALTER TABLE cash_bundles ADD CONSTRAINT in_or_out CHECK ((owner IS NULL) <> (withdrawal IS NULL));

-- migration #34
ALTER TABLE participants DROP CONSTRAINT participants_email_key;
CREATE UNIQUE INDEX participants_email_key ON participants (lower(email));
ALTER TABLE emails DROP CONSTRAINT emails_address_verified_key;
CREATE UNIQUE INDEX emails_address_verified_key ON emails (lower(address), verified);

-- migration #35
ALTER TABLE elsewhere ADD COLUMN domain text NOT NULL DEFAULT '';
ALTER TABLE elsewhere ALTER COLUMN domain DROP DEFAULT;
DROP INDEX elsewhere_lower_platform_idx;
CREATE UNIQUE INDEX elsewhere_user_name_key ON elsewhere (lower(user_name), platform, domain);
ALTER TABLE elsewhere DROP CONSTRAINT elsewhere_platform_user_id_key;
CREATE UNIQUE INDEX elsewhere_user_id_key ON elsewhere (platform, domain, user_id);
CREATE TABLE oauth_apps
( platform   text          NOT NULL
, domain     text          NOT NULL
, key        text          NOT NULL
, secret     text          NOT NULL
, ctime      timestamptz   NOT NULL DEFAULT CURRENT_TIMESTAMP
, UNIQUE (platform, domain, key)
);
INSERT INTO app_conf (key, value) VALUES
    ('app_name', '"Liberapay Dev"'::jsonb);

-- migration #36
ALTER TABLE elsewhere
    ALTER COLUMN user_id DROP NOT NULL,
    ADD CONSTRAINT user_id_chk CHECK (user_id IS NOT NULL OR domain <> '' AND user_name IS NOT NULL);

-- migration #37
ALTER TABLE participants ADD COLUMN throttle_takes boolean NOT NULL DEFAULT TRUE;

-- migration #38
CREATE TABLE repositories
( id                    bigserial       PRIMARY KEY
, platform              text            NOT NULL
, remote_id             text            NOT NULL
, owner_id              text            NOT NULL
, name                  text            NOT NULL
, slug                  text            NOT NULL
, description           text
, last_update           timestamptz     NOT NULL
, is_fork               boolean
, stars_count           int
, extra_info            json
, info_fetched_at       timestamptz     NOT NULL DEFAULT now()
, participant           bigint          REFERENCES participants
, show_on_profile       boolean         NOT NULL DEFAULT FALSE
, UNIQUE (platform, remote_id)
, UNIQUE (platform, slug)
);
CREATE INDEX repositories_trgm_idx ON repositories
    USING gist(name gist_trgm_ops);
INSERT INTO app_conf (key, value) VALUES
    ('refetch_repos_every', '60'::jsonb);

-- migration #39
ALTER TABLE paydays
    ADD COLUMN stage int,
    ALTER COLUMN stage SET DEFAULT 1;
INSERT INTO app_conf VALUES
    ('s3_payday_logs_bucket', '""'::jsonb),
    ('bot_github_username', '"liberapay-bot"'::jsonb),
    ('bot_github_token', '""'::jsonb),
    ('payday_repo', '"liberapay-bot/test"'::jsonb),
    ('payday_label', '"Payday"'::jsonb);
ALTER TABLE paydays ADD COLUMN public_log text;
UPDATE paydays SET public_log = '';
ALTER TABLE paydays ALTER COLUMN public_log SET NOT NULL;
ALTER TABLE paydays
    ALTER COLUMN ts_start DROP DEFAULT,
    ALTER COLUMN ts_start DROP NOT NULL;

-- migration #40
ALTER TABLE cash_bundles ADD COLUMN disputed boolean;
ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'chargeback';
CREATE TABLE disputes
( id              bigint          PRIMARY KEY
, creation_date   timestamptz     NOT NULL
, type            text            NOT NULL
, amount          numeric(35,2)   NOT NULL
, status          text            NOT NULL
, result_code     text
, exchange_id     int             NOT NULL REFERENCES exchanges
, participant     bigint          NOT NULL REFERENCES participants
);
CREATE TYPE debt_status AS ENUM ('due', 'paid', 'void');
CREATE TABLE debts
( id              serial          PRIMARY KEY
, debtor          bigint          NOT NULL REFERENCES participants
, creditor        bigint          NOT NULL REFERENCES participants
, amount          numeric(35,2)   NOT NULL
, origin          int             NOT NULL REFERENCES exchanges
, status          debt_status     NOT NULL
, settlement      int             REFERENCES transfers
, CONSTRAINT settlement_chk CHECK ((status = 'paid') = (settlement IS NOT NULL))
);
ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'debt';
ALTER TABLE cash_bundles ADD COLUMN locked_for int REFERENCES transfers;
CREATE OR REPLACE FUNCTION get_username(p_id bigint) RETURNS text
AS $$
    SELECT username FROM participants WHERE id = p_id;
$$ LANGUAGE sql;

-- migration #41
ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'account-switch';
ALTER TABLE transfers
    DROP CONSTRAINT self_chk,
    ADD CONSTRAINT self_chk CHECK ((tipper <> tippee) = (context <> 'account-switch'));
CREATE TABLE mangopay_users
( id            text     PRIMARY KEY
, participant   bigint   NOT NULL REFERENCES participants
);
CREATE OR REPLACE FUNCTION upsert_mangopay_user_id() RETURNS trigger AS $$
    BEGIN
        INSERT INTO mangopay_users
                    (id, participant)
             VALUES (NEW.mangopay_user_id, NEW.id)
        ON CONFLICT (id) DO NOTHING;
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER upsert_mangopay_user_id
    AFTER INSERT OR UPDATE OF mangopay_user_id ON participants
    FOR EACH ROW WHEN (NEW.mangopay_user_id IS NOT NULL)
    EXECUTE PROCEDURE upsert_mangopay_user_id();
INSERT INTO mangopay_users
            (id, participant)
     SELECT p.mangopay_user_id, p.id
       FROM participants p
      WHERE p.mangopay_user_id IS NOT NULL;
ALTER TABLE transfers
    ADD COLUMN wallet_from text,
    ADD COLUMN wallet_to text;
UPDATE transfers t
   SET wallet_from = (SELECT p.mangopay_wallet_id FROM participants p WHERE p.id = t.tipper)
     , wallet_to = (SELECT p.mangopay_wallet_id FROM participants p WHERE p.id = t.tippee)
     ;
ALTER TABLE transfers
    ALTER COLUMN wallet_from SET NOT NULL,
    ALTER COLUMN wallet_to SET NOT NULL,
    ADD CONSTRAINT wallets_chk CHECK (wallet_from <> wallet_to);
ALTER TABLE exchange_routes ADD COLUMN remote_user_id text;
UPDATE exchange_routes r SET remote_user_id = (SELECT p.mangopay_user_id FROM participants p WHERE p.id = r.participant);
ALTER TABLE exchange_routes ALTER COLUMN remote_user_id SET NOT NULL;
DROP VIEW current_exchange_routes CASCADE;
CREATE VIEW current_exchange_routes AS
    SELECT DISTINCT ON (participant, network) *
      FROM exchange_routes
  ORDER BY participant, network, id DESC;
CREATE CAST (current_exchange_routes AS exchange_routes) WITH INOUT;
ALTER TABLE cash_bundles ADD COLUMN wallet_id text;
UPDATE cash_bundles b
   SET wallet_id = (SELECT p.mangopay_wallet_id FROM participants p WHERE p.id = b.owner)
 WHERE owner IS NOT NULL;
ALTER TABLE cash_bundles
    ALTER COLUMN wallet_id DROP DEFAULT,
    ADD CONSTRAINT wallet_chk CHECK ((wallet_id IS NULL) = (owner IS NULL));
ALTER TABLE exchanges ADD COLUMN wallet_id text;
UPDATE exchanges e
   SET wallet_id = (SELECT p.mangopay_wallet_id FROM participants p WHERE p.id = e.participant);
ALTER TABLE exchanges
    ALTER COLUMN wallet_id DROP DEFAULT,
    ALTER COLUMN wallet_id SET NOT NULL;

-- migration #42
DELETE FROM app_conf WHERE key = 'update_global_stats_every';

-- migration #43
ALTER TABLE statements
    ADD COLUMN id bigserial PRIMARY KEY,
    ADD COLUMN ctime timestamptz NOT NULL DEFAULT '1970-01-01T00:00:00+00'::timestamptz,
    ADD COLUMN mtime timestamptz NOT NULL DEFAULT '1970-01-01T00:00:00+00'::timestamptz;
ALTER TABLE statements
    ALTER COLUMN ctime DROP DEFAULT,
    ALTER COLUMN mtime DROP DEFAULT;

-- migration #44
ALTER TABLE notification_queue ADD COLUMN ts timestamptz;
ALTER TABLE notification_queue ALTER COLUMN ts SET DEFAULT now();

-- migration #45
INSERT INTO app_conf (key, value) VALUES
    ('twitch_id', '"9ro3g4slh0de5yijy6rqb2p0jgd7hi"'::jsonb),
    ('twitch_secret', '"o090sc7828d7gljtrqc5n4vcpx3bfx"'::jsonb);

-- migration #46
ALTER TABLE notification_queue
    ADD COLUMN email boolean NOT NULL DEFAULT FALSE,
    ADD COLUMN web boolean NOT NULL DEFAULT TRUE,
    ADD CONSTRAINT destination_chk CHECK (email OR web),
    ADD COLUMN email_sent boolean;
ALTER TABLE notification_queue RENAME TO notifications;
CREATE UNIQUE INDEX queued_emails_idx ON notifications (id ASC)
    WHERE (email AND email_sent IS NOT true);
ALTER TABLE notifications
    ALTER COLUMN email DROP DEFAULT,
    ALTER COLUMN web DROP DEFAULT;
DROP TABLE email_queue;

-- migration #47
DROP VIEW current_exchange_routes CASCADE;
ALTER TABLE exchange_routes ADD COLUMN ctime timestamptz;
UPDATE exchange_routes r
       SET ctime = (
               SELECT min(e.timestamp)
                 FROM exchanges e
                WHERE e.route = r.id
           )
     WHERE ctime IS NULL;
ALTER TABLE exchange_routes ALTER COLUMN ctime SET DEFAULT now();

-- migration #48
ALTER TABLE exchange_routes ADD COLUMN mandate text CHECK (mandate <> '');
ALTER TYPE exchange_status ADD VALUE IF NOT EXISTS 'pre-mandate';
INSERT INTO app_conf (key, value) VALUES
    ('show_sandbox_warning', 'true'::jsonb);

-- migration #49
ALTER TABLE exchanges ADD COLUMN remote_id text;
ALTER TABLE exchanges
    ADD CONSTRAINT remote_id_null_chk CHECK ((status::text LIKE 'pre%') = (remote_id IS NULL)),
    ADD CONSTRAINT remote_id_empty_chk CHECK (NOT (status <> 'failed' AND remote_id = ''));

-- migration #50
CREATE UNLOGGED TABLE rate_limiting
( key       text          PRIMARY KEY
, counter   int           NOT NULL
, ts        timestamptz   NOT NULL
);
CREATE OR REPLACE FUNCTION compute_leak(cap int, period float, last_leak timestamptz) RETURNS int AS $$
    SELECT trunc(cap * extract(epoch FROM current_timestamp - last_leak) / period)::int;
$$ LANGUAGE sql STABLE;
CREATE OR REPLACE FUNCTION hit_rate_limit(key text, cap int, period float) RETURNS int AS $$
    INSERT INTO rate_limiting AS r
                (key, counter, ts)
         VALUES (key, 1, current_timestamp)
    ON CONFLICT (key) DO UPDATE
            SET counter = r.counter + 1 - least(compute_leak(cap, period, r.ts), r.counter)
              , ts = current_timestamp
          WHERE (r.counter - compute_leak(cap, period, r.ts)) < cap
      RETURNING cap - counter;
$$ LANGUAGE sql;
CREATE OR REPLACE FUNCTION clean_up_counters(pattern text, period float) RETURNS bigint AS $$
    WITH deleted AS (
        DELETE FROM rate_limiting
              WHERE key LIKE pattern
                AND ts < (current_timestamp - make_interval(secs => period))
          RETURNING 1
    ) SELECT count(*) FROM deleted;
$$ LANGUAGE sql;
INSERT INTO app_conf (key, value) VALUES
    ('clean_up_counters_every', '3600'::jsonb),
    ('trusted_proxies', '[]'::jsonb);

-- migration #51
CREATE TABLE redirections
( from_prefix   text          PRIMARY KEY
, to_prefix     text          NOT NULL
, ctime         timestamptz   NOT NULL DEFAULT now()
, mtime         timestamptz   NOT NULL DEFAULT now()
);
CREATE INDEX redirections_to_prefix_idx ON redirections (to_prefix);

-- migration #52
ALTER TYPE stmt_type ADD VALUE IF NOT EXISTS 'summary';

-- migration #53
ALTER TABLE takes ADD COLUMN actual_amount numeric(35,2);
ALTER TABLE participants
    ADD COLUMN nteampatrons int NOT NULL DEFAULT 0,
    ADD COLUMN leftover numeric(35,2) NOT NULL DEFAULT 0 CHECK (leftover >= 0),
    ADD CONSTRAINT receiving_chk CHECK (receiving >= 0),
    ADD CONSTRAINT taking_chk CHECK (taking >= 0);
CREATE OR REPLACE VIEW current_takes AS
    SELECT * FROM (
         SELECT DISTINCT ON (member, team) t.*
           FROM takes t
       ORDER BY member, team, mtime DESC
    ) AS anon WHERE amount IS NOT NULL;
INSERT INTO app_conf VALUES ('update_cached_amounts_every', '86400'::jsonb);
ALTER TABLE takes ADD CONSTRAINT null_amounts_chk CHECK ((actual_amount IS NULL) = (amount IS NULL));

-- migration #54
CREATE TYPE currency AS ENUM ('EUR', 'USD');
CREATE TYPE currency_amount AS (amount numeric, currency currency);
CREATE FUNCTION currency_amount_add(currency_amount, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount + $2.amount, $1.currency);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR + (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_add,
    commutator = +
);
CREATE FUNCTION currency_amount_sub(currency_amount, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount - $2.amount, $1.currency);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR - (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_sub
);
CREATE FUNCTION currency_amount_neg(currency_amount)
RETURNS currency_amount AS $$
    BEGIN RETURN (-$1.amount, $1.currency); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR - (
    rightarg = currency_amount,
    procedure = currency_amount_neg
);
CREATE FUNCTION currency_amount_mul(currency_amount, numeric)
RETURNS currency_amount AS $$
    BEGIN
        RETURN ($1.amount * $2, $1.currency);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR * (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_mul,
    commutator = *
);
CREATE AGGREGATE sum(currency_amount) (
    sfunc = currency_amount_add,
    stype = currency_amount
);
CREATE FUNCTION get_currency(currency_amount) RETURNS currency AS $$
    BEGIN RETURN $1.currency; END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE CAST (currency_amount as currency) WITH FUNCTION get_currency(currency_amount);
CREATE FUNCTION zero(currency) RETURNS currency_amount AS $$
    BEGIN RETURN ('0.00'::numeric, $1); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE FUNCTION zero(currency_amount) RETURNS currency_amount AS $$
    BEGIN RETURN ('0.00'::numeric, $1.currency); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE FUNCTION currency_amount_eq(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN RETURN ($1.currency = $2.currency AND $1.amount = $2.amount); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR = (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_eq,
    commutator = =
);
CREATE FUNCTION currency_amount_ne(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN RETURN ($1.currency <> $2.currency OR $1.amount <> $2.amount); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR <> (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_ne,
    commutator = <>
);
CREATE FUNCTION currency_amount_gt(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount > $2.amount);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR > (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_gt,
    commutator = <,
    negator = <=
);
CREATE FUNCTION currency_amount_gte(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount >= $2.amount);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR >= (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_gte,
    commutator = <=,
    negator = <
);
CREATE FUNCTION currency_amount_lt(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount < $2.amount);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR < (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_lt,
    commutator = >,
    negator = >=
);
CREATE FUNCTION currency_amount_lte(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount <= $2.amount);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR <= (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_lte,
    commutator = >=,
    negator = >
);
CREATE FUNCTION currency_amount_eq_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount = $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR = (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_eq_numeric,
    commutator = =
);
CREATE FUNCTION currency_amount_ne_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount <> $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR <> (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_ne_numeric,
    commutator = <>
);
CREATE FUNCTION currency_amount_gt_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount > $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR > (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_gt_numeric,
    commutator = <,
    negator = <=
);
CREATE FUNCTION currency_amount_gte_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount >= $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR >= (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_gte_numeric,
    commutator = <=,
    negator = <
);
CREATE FUNCTION currency_amount_lt_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount < $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR < (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_lt_numeric,
    commutator = >,
    negator = >=
);
CREATE FUNCTION currency_amount_lte_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount <= $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR <= (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_lte_numeric,
    commutator = >=,
    negator = >
);
CREATE TYPE currency_basket AS (EUR numeric, USD numeric);
CREATE FUNCTION currency_basket_add(currency_basket, currency_amount)
RETURNS currency_basket AS $$
    BEGIN
        IF ($2.currency = 'EUR') THEN
            RETURN ($1.EUR + $2.amount, $1.USD);
        ELSIF ($2.currency = 'USD') THEN
            RETURN ($1.EUR, $1.USD + $2.amount);
        ELSE
            RAISE 'unknown currency %', $2.currency;
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR + (
    leftarg = currency_basket,
    rightarg = currency_amount,
    procedure = currency_basket_add,
    commutator = +
);
CREATE FUNCTION currency_basket_add(currency_basket, currency_basket)
RETURNS currency_basket AS $$
    BEGIN RETURN ($1.EUR + $2.EUR, $1.USD + $2.USD); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR + (
    leftarg = currency_basket,
    rightarg = currency_basket,
    procedure = currency_basket_add,
    commutator = +
);
CREATE FUNCTION currency_basket_sub(currency_basket, currency_amount)
RETURNS currency_basket AS $$
    BEGIN
        IF ($2.currency = 'EUR') THEN
            RETURN ($1.EUR - $2.amount, $1.USD);
        ELSIF ($2.currency = 'USD') THEN
            RETURN ($1.EUR, $1.USD - $2.amount);
        ELSE
            RAISE 'unknown currency %', $2.currency;
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR - (
    leftarg = currency_basket,
    rightarg = currency_amount,
    procedure = currency_basket_sub
);
CREATE FUNCTION currency_basket_sub(currency_basket, currency_basket)
RETURNS currency_basket AS $$
    BEGIN RETURN ($1.EUR - $2.EUR, $1.USD - $2.USD); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR - (
    leftarg = currency_basket,
    rightarg = currency_basket,
    procedure = currency_basket_sub
);
CREATE FUNCTION currency_basket_contains(currency_basket, currency_amount)
RETURNS boolean AS $$
    BEGIN
        IF ($2.currency = 'EUR') THEN
            RETURN ($1.EUR >= $2.amount);
        ELSIF ($2.currency = 'USD') THEN
            RETURN ($1.USD >= $2.amount);
        ELSE
            RAISE 'unknown currency %', $2.currency;
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR >= (
    leftarg = currency_basket,
    rightarg = currency_amount,
    procedure = currency_basket_contains
);
CREATE AGGREGATE basket_sum(currency_amount) (
    sfunc = currency_basket_add,
    stype = currency_basket,
    initcond = '(0.00,0.00)'
);
CREATE TABLE currency_exchange_rates
( source_currency   currency   NOT NULL
, target_currency   currency   NOT NULL
, rate              numeric    NOT NULL
, UNIQUE (source_currency, target_currency)
);
CREATE FUNCTION convert(currency_amount, currency) RETURNS currency_amount AS $$
    DECLARE
        rate numeric;
    BEGIN
        IF ($1.currency = $2) THEN RETURN $1; END IF;
        rate := (
            SELECT r.rate
              FROM currency_exchange_rates r
             WHERE r.source_currency = $1.currency
        );
        IF (rate IS NULL) THEN
            RAISE 'missing exchange rate %->%', $1.currency, $2;
        END IF;
        RETURN ($1.amount / rate, $2);
    END;
$$ LANGUAGE plpgsql STRICT;
CREATE FUNCTION currency_amount_fuzzy_sum_sfunc(
    currency_amount, currency_amount, currency
) RETURNS currency_amount AS $$
    BEGIN RETURN ($1.amount + (convert($2, $3)).amount, $3); END;
$$ LANGUAGE plpgsql STRICT;
CREATE AGGREGATE sum(currency_amount, currency) (
    sfunc = currency_amount_fuzzy_sum_sfunc,
    stype = currency_amount,
    initcond = '(0,)'
);
CREATE TYPE currency_amount_fuzzy_avg_state AS (
    _sum numeric, _count int, target currency
);
CREATE FUNCTION currency_amount_fuzzy_avg_sfunc(
    currency_amount_fuzzy_avg_state, currency_amount, currency
) RETURNS currency_amount_fuzzy_avg_state AS $$
    BEGIN
        IF ($2.currency = $3) THEN
            RETURN ($1._sum + $2.amount, $1._count + 1, $3);
        END IF;
        RETURN ($1._sum + (convert($2, $3)).amount, $1._count + 1, $3);
    END;
$$ LANGUAGE plpgsql STRICT;
CREATE FUNCTION currency_amount_fuzzy_avg_ffunc(currency_amount_fuzzy_avg_state)
RETURNS currency_amount AS $$
    BEGIN RETURN ((CASE WHEN $1._count = 0 THEN 0 ELSE $1._sum / $1._count END), $1.target); END;
$$ LANGUAGE plpgsql STRICT;
CREATE AGGREGATE avg(currency_amount, currency) (
    sfunc = currency_amount_fuzzy_avg_sfunc,
    finalfunc = currency_amount_fuzzy_avg_ffunc,
    stype = currency_amount_fuzzy_avg_state,
    initcond = '(0,0,)'
);
ALTER TABLE participants ADD COLUMN main_currency currency NOT NULL DEFAULT 'EUR';
ALTER TABLE participants ADD COLUMN accept_all_currencies boolean;
UPDATE participants
   SET accept_all_currencies = true
 WHERE status = 'stub';
ALTER TABLE cash_bundles ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
ALTER TABLE debts ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
ALTER TABLE disputes ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
ALTER TABLE exchanges ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
ALTER TABLE exchanges ALTER COLUMN fee TYPE currency_amount USING (fee, 'EUR');
ALTER TABLE exchanges ALTER COLUMN vat TYPE currency_amount USING (vat, 'EUR');
ALTER TABLE invoices ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
ALTER TABLE transfers ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
DROP VIEW current_tips;
ALTER TABLE tips ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
ALTER TABLE tips ALTER COLUMN periodic_amount TYPE currency_amount USING (periodic_amount, 'EUR');
CREATE VIEW current_tips AS
        SELECT DISTINCT ON (tipper, tippee) *
          FROM tips
      ORDER BY tipper, tippee, mtime DESC;
CREATE TABLE wallets
    ( remote_id         text              NOT NULL UNIQUE
    , balance           currency_amount   NOT NULL CHECK (balance >= 0)
    , owner             bigint            NOT NULL REFERENCES participants
    , remote_owner_id   text              NOT NULL
    , is_current        boolean           DEFAULT TRUE
    );
CREATE UNIQUE INDEX ON wallets (owner, (balance::currency), is_current);
CREATE UNIQUE INDEX ON wallets (remote_owner_id, (balance::currency));
INSERT INTO wallets
                (remote_id, balance, owner, remote_owner_id)
         SELECT p.mangopay_wallet_id
              , (p.balance, 'EUR')::currency_amount
              , p.id
              , p.mangopay_user_id
           FROM participants p
          WHERE p.mangopay_wallet_id IS NOT NULL;
INSERT INTO wallets
                (remote_id, balance, owner, remote_owner_id, is_current)
         SELECT e.payload->'old_wallet_id'
              , ('0.00', 'EUR')::currency_amount
              , e.participant
              , e.payload->'old_user_id'
              , false
           FROM "events" e
          WHERE e.type = 'mangopay-account-change';
CREATE FUNCTION EUR(numeric) RETURNS currency_amount AS $$
    BEGIN RETURN ($1, 'EUR'); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
DROP VIEW sponsors;
ALTER TABLE participants DROP COLUMN mangopay_wallet_id;
ALTER TABLE participants
        ALTER COLUMN goal DROP DEFAULT,
        ALTER COLUMN goal TYPE currency_amount USING EUR(goal),
        ALTER COLUMN goal SET DEFAULT NULL;
ALTER TABLE participants
        ALTER COLUMN giving DROP DEFAULT,
        ALTER COLUMN giving TYPE currency_amount USING EUR(giving);
ALTER TABLE participants
        ALTER COLUMN receiving DROP DEFAULT,
        ALTER COLUMN receiving TYPE currency_amount USING EUR(receiving);
ALTER TABLE participants
        ALTER COLUMN taking DROP DEFAULT,
        ALTER COLUMN taking TYPE currency_amount USING EUR(taking);
ALTER TABLE participants
        ALTER COLUMN leftover DROP DEFAULT,
        ALTER COLUMN leftover TYPE currency_amount USING EUR(leftover);
ALTER TABLE participants
        ALTER COLUMN balance DROP DEFAULT,
        ALTER COLUMN balance TYPE currency_amount USING EUR(balance);
CREATE FUNCTION initialize_amounts() RETURNS trigger AS $$
        BEGIN
            NEW.giving = COALESCE(NEW.giving, zero(NEW.main_currency));
            NEW.receiving = COALESCE(NEW.receiving, zero(NEW.main_currency));
            NEW.taking = COALESCE(NEW.taking, zero(NEW.main_currency));
            NEW.leftover = COALESCE(NEW.leftover, zero(NEW.main_currency));
            NEW.balance = COALESCE(NEW.balance, zero(NEW.main_currency));
            RETURN NEW;
        END;
    $$ LANGUAGE plpgsql;
CREATE TRIGGER initialize_amounts BEFORE INSERT ON participants
        FOR EACH ROW EXECUTE PROCEDURE initialize_amounts();
CREATE VIEW sponsors AS
        SELECT *
          FROM participants p
         WHERE status = 'active'
           AND kind = 'organization'
           AND giving > receiving
           AND giving >= 10
           AND hide_from_lists = 0
           AND profile_noindex = 0
        ;
DROP VIEW current_takes;
ALTER TABLE takes
        ALTER COLUMN amount DROP DEFAULT,
        ALTER COLUMN amount TYPE currency_amount USING EUR(amount),
        ALTER COLUMN amount SET DEFAULT NULL;
ALTER TABLE takes
        ALTER COLUMN actual_amount DROP DEFAULT,
        ALTER COLUMN actual_amount TYPE currency_amount USING EUR(actual_amount),
        ALTER COLUMN actual_amount SET DEFAULT NULL;
CREATE VIEW current_takes AS
        SELECT * FROM (
             SELECT DISTINCT ON (member, team) t.*
               FROM takes t
           ORDER BY member, team, mtime DESC
        ) AS anon WHERE amount IS NOT NULL;
DROP FUNCTION EUR(numeric);
ALTER TABLE paydays
        ALTER COLUMN transfer_volume DROP DEFAULT,
        ALTER COLUMN transfer_volume TYPE currency_basket USING (transfer_volume, '0.00'),
        ALTER COLUMN transfer_volume SET DEFAULT ('0.00', '0.00');
ALTER TABLE paydays
        ALTER COLUMN take_volume DROP DEFAULT,
        ALTER COLUMN take_volume TYPE currency_basket USING (take_volume, '0.00'),
        ALTER COLUMN take_volume SET DEFAULT ('0.00', '0.00');
ALTER TABLE paydays
        ALTER COLUMN week_deposits DROP DEFAULT,
        ALTER COLUMN week_deposits TYPE currency_basket USING (week_deposits, '0.00'),
        ALTER COLUMN week_deposits SET DEFAULT ('0.00', '0.00');
ALTER TABLE paydays
        ALTER COLUMN week_withdrawals DROP DEFAULT,
        ALTER COLUMN week_withdrawals TYPE currency_basket USING (week_withdrawals, '0.00'),
        ALTER COLUMN week_withdrawals SET DEFAULT ('0.00', '0.00');
ALTER TABLE paydays
        ALTER COLUMN transfer_volume_refunded DROP DEFAULT,
        ALTER COLUMN transfer_volume_refunded TYPE currency_basket USING (transfer_volume_refunded, '0.00'),
        ALTER COLUMN transfer_volume_refunded SET DEFAULT ('0.00', '0.00');
ALTER TABLE paydays
        ALTER COLUMN week_deposits_refunded DROP DEFAULT,
        ALTER COLUMN week_deposits_refunded TYPE currency_basket USING (week_deposits_refunded, '0.00'),
        ALTER COLUMN week_deposits_refunded SET DEFAULT ('0.00', '0.00');
ALTER TABLE paydays
        ALTER COLUMN week_withdrawals_refunded DROP DEFAULT,
        ALTER COLUMN week_withdrawals_refunded TYPE currency_basket USING (week_withdrawals_refunded, '0.00'),
        ALTER COLUMN week_withdrawals_refunded SET DEFAULT ('0.00', '0.00');
CREATE FUNCTION recompute_balance(bigint) RETURNS currency_amount AS $$
    UPDATE participants p
       SET balance = (
               SELECT sum(w.balance, p.main_currency)
                 FROM wallets w
                WHERE w.owner = p.id
           )
     WHERE id = $1
 RETURNING balance;
$$ LANGUAGE SQL STRICT;
DELETE FROM notifications WHERE event = 'low_balance';
ALTER TABLE balances_at ALTER COLUMN balance TYPE currency_basket USING (balance, '0.00');
ALTER TABLE balances_at RENAME COLUMN balance TO balances;
ALTER TABLE exchange_routes ADD COLUMN currency currency;
UPDATE exchange_routes SET currency = 'EUR' WHERE network = 'mango-cc';
ALTER TABLE exchange_routes ADD CONSTRAINT currency_chk CHECK ((currency IS NULL) = (network <> 'mango-cc'));

-- migration #55
CREATE FUNCTION coalesce_currency_amount(currency_amount, currency) RETURNS currency_amount AS $$
    BEGIN RETURN (COALESCE($1.amount, '0.00'::numeric), COALESCE($1.currency, $2)); END;
$$ LANGUAGE plpgsql IMMUTABLE;
CREATE OR REPLACE FUNCTION initialize_amounts() RETURNS trigger AS $$
    BEGIN
        NEW.giving = coalesce_currency_amount(NEW.giving, NEW.main_currency);
        NEW.receiving = coalesce_currency_amount(NEW.receiving, NEW.main_currency);
        NEW.taking = coalesce_currency_amount(NEW.taking, NEW.main_currency);
        NEW.leftover = coalesce_currency_amount(NEW.leftover, NEW.main_currency);
        NEW.balance = coalesce_currency_amount(NEW.balance, NEW.main_currency);
        RETURN NEW;
    END;
$$ LANGUAGE plpgsql;
DROP TRIGGER initialize_amounts ON participants;
CREATE TRIGGER initialize_amounts
    BEFORE INSERT OR UPDATE ON participants
    FOR EACH ROW EXECUTE PROCEDURE initialize_amounts();

-- migration #56
DELETE FROM app_conf WHERE key = 'update_cached_amounts_every';

-- migration #57
CREATE OR REPLACE FUNCTION round(currency_amount) RETURNS currency_amount AS $$
    BEGIN RETURN (round($1.amount, 2), $1.currency); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OR REPLACE FUNCTION convert(currency_amount, currency, boolean) RETURNS currency_amount AS $$
    DECLARE
        rate numeric;
        result currency_amount;
    BEGIN
        IF ($1.currency = $2) THEN RETURN $1; END IF;
        rate := (
            SELECT r.rate
              FROM currency_exchange_rates r
             WHERE r.source_currency = $1.currency
        );
        IF (rate IS NULL) THEN
            RAISE 'missing exchange rate %->%', $1.currency, $2;
        END IF;
        result := ($1.amount / rate, $2);
        RETURN (CASE WHEN $3 THEN round(result) ELSE result END);
    END;
$$ LANGUAGE plpgsql STRICT;
CREATE OR REPLACE FUNCTION convert(currency_amount, currency) RETURNS currency_amount AS $$
    BEGIN RETURN convert($1, $2, true); END;
$$ LANGUAGE plpgsql STRICT;
CREATE OR REPLACE FUNCTION currency_amount_fuzzy_sum_sfunc(
    currency_amount, currency_amount, currency
) RETURNS currency_amount AS $$
    BEGIN RETURN ($1.amount + (convert($2, $3, false)).amount, $3); END;
$$ LANGUAGE plpgsql STRICT;
DROP AGGREGATE sum(currency_amount, currency);
CREATE AGGREGATE sum(currency_amount, currency) (
    sfunc = currency_amount_fuzzy_sum_sfunc,
    finalfunc = round,
    stype = currency_amount,
    initcond = '(0,)'
);
CREATE OR REPLACE FUNCTION currency_amount_fuzzy_avg_sfunc(
    currency_amount_fuzzy_avg_state, currency_amount, currency
) RETURNS currency_amount_fuzzy_avg_state AS $$
    BEGIN
        IF ($2.currency = $3) THEN
            RETURN ($1._sum + $2.amount, $1._count + 1, $3);
        END IF;
        RETURN ($1._sum + (convert($2, $3, false)).amount, $1._count + 1, $3);
    END;
$$ LANGUAGE plpgsql STRICT;
CREATE OR REPLACE FUNCTION currency_amount_fuzzy_avg_ffunc(currency_amount_fuzzy_avg_state)
RETURNS currency_amount AS $$
    BEGIN RETURN round(
        ((CASE WHEN $1._count = 0 THEN 0 ELSE $1._sum / $1._count END), $1.target)::currency_amount
    ); END;
$$ LANGUAGE plpgsql STRICT;

-- migration #58
UPDATE wallets
   SET is_current = true
  FROM participants p
 WHERE p.id = owner
   AND p.mangopay_user_id = remote_owner_id
   AND is_current IS NULL;

-- migration #59
UPDATE participants
   SET email_lang = (
           SELECT l
             FROM ( SELECT regexp_replace(x, '[-;].*', '') AS l
                      FROM regexp_split_to_table(email_lang, ',') x
                  ) x
            WHERE l IN ('ca', 'cs', 'da', 'de', 'el', 'en', 'eo', 'es', 'et', 'fi',
                        'fr', 'fy', 'hu', 'id', 'it', 'ja', 'ko', 'nb', 'nl', 'pl',
                        'pt', 'ru', 'sl', 'sv', 'tr', 'uk', 'zh')
            LIMIT 1
       )
 WHERE length(email_lang) > 0;

-- migration #60
CREATE OR REPLACE FUNCTION convert(currency_amount, currency, boolean) RETURNS currency_amount AS $$
    DECLARE
        rate numeric;
        result currency_amount;
    BEGIN
        IF ($1.currency = $2) THEN RETURN $1; END IF;
        rate := (
            SELECT r.rate
              FROM currency_exchange_rates r
             WHERE r.source_currency = $1.currency
        );
        IF (rate IS NULL) THEN
            RAISE 'missing exchange rate %->%', $1.currency, $2;
        END IF;
        result := ($1.amount * rate, $2);
        RETURN (CASE WHEN $3 THEN round(result) ELSE result END);
    END;
$$ LANGUAGE plpgsql STRICT;

-- migration #61
ALTER TABLE participants ADD COLUMN accepted_currencies text;
UPDATE participants
   SET accepted_currencies = (
           CASE WHEN accept_all_currencies THEN 'EUR,USD' ELSE main_currency::text END
       )
 WHERE status <> 'stub';
DROP VIEW sponsors;
CREATE OR REPLACE VIEW sponsors AS
    SELECT username, giving, avatar_url
      FROM participants p
     WHERE status = 'active'
       AND kind = 'organization'
       AND giving > receiving
       AND giving >= 10
       AND hide_from_lists = 0
       AND profile_noindex = 0
    ;
ALTER TABLE participants DROP COLUMN accept_all_currencies;

-- migration #62
CREATE FUNCTION make_currency_basket(currency_amount) RETURNS currency_basket AS $$
    BEGIN RETURN (CASE
        WHEN $1.currency = 'EUR' THEN ($1.amount, '0.00'::numeric)
                                 ELSE ('0.00'::numeric, $1.amount)
    END); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE CAST (currency_amount as currency_basket) WITH FUNCTION make_currency_basket(currency_amount);
CREATE FUNCTION make_currency_basket_or_null(currency_amount) RETURNS currency_basket AS $$
    BEGIN RETURN (CASE WHEN $1.amount = 0 THEN NULL ELSE make_currency_basket($1) END); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
ALTER TABLE participants
    DROP CONSTRAINT participants_leftover_check,
    ALTER COLUMN leftover DROP NOT NULL,
    ALTER COLUMN leftover TYPE currency_basket USING make_currency_basket_or_null(leftover);
DROP FUNCTION make_currency_basket_or_null(currency_amount);
DROP VIEW current_takes;
ALTER TABLE takes
    ALTER COLUMN actual_amount TYPE currency_basket USING actual_amount::currency_basket;
CREATE VIEW current_takes AS
    SELECT * FROM (
         SELECT DISTINCT ON (member, team) t.*
           FROM takes t
       ORDER BY member, team, mtime DESC
    ) AS anon WHERE amount IS NOT NULL;
CREATE OR REPLACE FUNCTION initialize_amounts() RETURNS trigger AS $$
    BEGIN
        NEW.giving = coalesce_currency_amount(NEW.giving, NEW.main_currency);
        NEW.receiving = coalesce_currency_amount(NEW.receiving, NEW.main_currency);
        NEW.taking = coalesce_currency_amount(NEW.taking, NEW.main_currency);
        NEW.balance = coalesce_currency_amount(NEW.balance, NEW.main_currency);
        RETURN NEW;
    END;
$$ LANGUAGE plpgsql;
CREATE AGGREGATE sum(currency_basket) (
    sfunc = currency_basket_add,
    stype = currency_basket,
    initcond = '(0.00,0.00)'
);
CREATE FUNCTION empty_currency_basket() RETURNS currency_basket AS $$
    BEGIN RETURN ('0.00'::numeric, '0.00'::numeric); END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- migration #63
CREATE TABLE exchange_events
( id             bigserial         PRIMARY KEY
, timestamp      timestamptz       NOT NULL DEFAULT current_timestamp
, exchange       int               NOT NULL REFERENCES exchanges
, status         exchange_status   NOT NULL
, error          text
, wallet_delta   currency_amount
, UNIQUE (exchange, status)
);

-- migration #64
ALTER TABLE elsewhere
    ADD COLUMN info_fetched_at timestamptz NOT NULL DEFAULT '1970-01-01T00:00:00+00'::timestamptz,
    ALTER COLUMN info_fetched_at SET DEFAULT current_timestamp;
INSERT INTO app_conf VALUES
    ('refetch_elsewhere_data_every', '120'::jsonb);
CREATE OR REPLACE FUNCTION check_rate_limit(k text, cap int, period float) RETURNS boolean AS $$
    SELECT coalesce(
        ( SELECT counter - least(compute_leak(cap, period, r.ts), r.counter)
            FROM rate_limiting AS r
           WHERE r.key = k
        ), 0
    ) < cap;
$$ LANGUAGE sql;

-- migration #65
CREATE TABLE user_secrets
( participant   bigint        NOT NULL REFERENCES participants
, id            int           NOT NULL
, secret        text          NOT NULL
, mtime         timestamptz   NOT NULL DEFAULT current_timestamp
, UNIQUE (participant, id)
);
INSERT INTO user_secrets
     SELECT p.id, 0, p.password, p.password_mtime
       FROM participants p
      WHERE p.password IS NOT NULL
ON CONFLICT (participant, id) DO UPDATE
        SET secret = excluded.secret
          , mtime = excluded.mtime;
INSERT INTO user_secrets
     SELECT p.id, 1, p.session_token, p.session_expires - interval '6 hours'
       FROM participants p
      WHERE p.session_token IS NOT NULL
        AND p.session_expires >= (current_timestamp - interval '30 days')
ON CONFLICT (participant, id) DO UPDATE
        SET secret = excluded.secret
          , mtime = excluded.mtime;
ALTER TABLE participants
    DROP COLUMN password,
    DROP COLUMN password_mtime,
    DROP COLUMN session_token,
    DROP COLUMN session_expires;

-- migration #66
ALTER TABLE participants ADD COLUMN public_name text;

-- migration #67
ALTER TABLE elsewhere DROP COLUMN email;
ALTER TABLE elsewhere ADD COLUMN description text;
UPDATE elsewhere
       SET description = extra_info->>'bio'
     WHERE platform IN ('facebook', 'github', 'gitlab')
       AND length(extra_info->>'bio') > 0;
UPDATE elsewhere
       SET description = extra_info->>'aboutMe'
     WHERE platform = 'google'
       AND length(extra_info->>'aboutMe') > 0;
UPDATE elsewhere
       SET description = extra_info->>'note'
     WHERE platform = 'mastodon'
       AND length(extra_info->>'note') > 0;
UPDATE elsewhere
       SET description = extra_info->'osm'->'user'->>'description'
     WHERE platform = 'openstreetmap'
       AND length(extra_info->'osm'->'user'->>'description') > 0;
UPDATE elsewhere
       SET description = extra_info->>'description'
     WHERE platform IN ('twitch', 'twitter')
       AND length(extra_info->>'description') > 0;
UPDATE elsewhere
       SET description = extra_info->'snippet'->>'description'
     WHERE platform = 'youtube'
       AND length(extra_info->'snippet'->>'description') > 0;

-- migration #68
WITH zeroed_tips AS (
         SELECT t.id
           FROM events e
           JOIN current_tips t ON t.tippee = e.participant
                              AND t.mtime = e.ts
                              AND t.amount = 0
          WHERE e.type = 'set_status' AND e.payload = '"closed"'
             OR e.type = 'set_goal' AND e.payload::text LIKE '"-%"'
     )
DELETE FROM tips t WHERE EXISTS (SELECT 1 FROM zeroed_tips z WHERE z.id = t.id);
UPDATE events
   SET recorder = (payload->>'invitee')::int
 WHERE type IN ('invite_accept', 'invite_refuse');

-- migration #69
ALTER TYPE transfer_context ADD VALUE 'swap';
ALTER TABLE transfers ADD COLUMN counterpart int REFERENCES transfers;
ALTER TABLE transfers ADD CONSTRAINT counterpart_chk CHECK ((counterpart IS NULL) = (context <> 'swap') OR (context = 'swap' AND status <> 'succeeded'));
