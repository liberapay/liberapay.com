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

-- migration #70
ALTER TABLE tips ADD COLUMN paid_in_advance currency_amount;
ALTER TABLE tips ADD CONSTRAINT paid_in_advance_currency_chk CHECK (paid_in_advance::currency = amount::currency);
DROP VIEW current_tips;
CREATE VIEW current_tips AS
        SELECT DISTINCT ON (tipper, tippee) *
          FROM tips
      ORDER BY tipper, tippee, mtime DESC;
DROP FUNCTION update_tip();
ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'tip-in-advance';
ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'take-in-advance';
ALTER TABLE transfers ADD COLUMN unit_amount currency_amount;
ALTER TABLE transfers ADD CONSTRAINT unit_amount_currency_chk CHECK (unit_amount::currency = amount::currency);

-- migration #71
ALTER TABLE transfers ADD COLUMN virtual boolean;

-- migration #72
INSERT INTO app_conf VALUES ('payin_methods', '{"*": false, "bankwire": false, "card": true, "direct-debit": false}'::jsonb);

-- migration #73
INSERT INTO app_conf VALUES
    ('stripe_connect_id', '"ca_DEYxiYHBHZtGj32l9uczcsunbQOcRq8H"'::jsonb),
    ('stripe_secret_key', '"sk_test_QTUa8AqWXyU2feC32glNgDQd"'::jsonb);
ALTER TABLE participants ADD COLUMN has_payment_account boolean;
CREATE TABLE payment_accounts
( participant           bigint          NOT NULL REFERENCES participants
, provider              text            NOT NULL
, country               text            NOT NULL
, id                    text            NOT NULL CHECK (id <> '')
, is_current            boolean         DEFAULT TRUE CHECK (is_current IS NOT FALSE)
, charges_enabled       boolean         NOT NULL
, default_currency      text
, display_name          text
, token                 json
, connection_ts         timestamptz     NOT NULL DEFAULT current_timestamp
, UNIQUE (participant, provider, country, is_current)
, UNIQUE (provider, id, participant)
);
CREATE OR REPLACE FUNCTION update_has_payment_account() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := COALESCE(NEW, OLD);
        UPDATE participants
           SET has_payment_account = (
                   SELECT count(*)
                     FROM payment_accounts
                    WHERE participant = rec.participant
                      AND is_current IS TRUE
               ) > 0
         WHERE id = rec.participant;
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER update_has_payment_account
    AFTER INSERT OR UPDATE OR DELETE ON payment_accounts
    FOR EACH ROW EXECUTE PROCEDURE update_has_payment_account();

-- migration #74
ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'fee-refund';

-- migration #75
ALTER TYPE payment_net ADD VALUE IF NOT EXISTS 'stripe-card';
INSERT INTO app_conf VALUES
    ('stripe_publishable_key', '"pk_test_rGZY3Q7ba61df50X0h70iHeZ"'::jsonb);
UPDATE app_conf
   SET value = '{"*": true, "mango-ba": false, "mango-bw": false, "mango-cc": false, "stripe-card": true}'::jsonb
 WHERE key = 'payin_methods';
ALTER TABLE payment_accounts ADD COLUMN pk bigserial PRIMARY KEY;
CREATE TYPE payin_status AS ENUM (
    'pre', 'submitting', 'pending', 'succeeded', 'failed'
);
CREATE TABLE payins
( id               bigserial         PRIMARY KEY
, ctime            timestamptz       NOT NULL DEFAULT current_timestamp
, remote_id        text
, payer            bigint            NOT NULL REFERENCES participants
, amount           currency_amount   NOT NULL CHECK (amount > 0)
, status           payin_status      NOT NULL
, error            text
, route            int               NOT NULL REFERENCES exchange_routes
, amount_settled   currency_amount
, fee              currency_amount   CHECK (fee >= 0)
, CONSTRAINT fee_currency_chk CHECK (fee::currency = amount_settled::currency)
, CONSTRAINT success_chk CHECK (NOT (status = 'succeeded' AND (amount_settled IS NULL OR fee IS NULL)))
);
CREATE INDEX payins_payer_idx ON payins (payer);
CREATE TABLE payin_events
( payin          int               NOT NULL REFERENCES payins
, status         payin_status      NOT NULL
, error          text
, timestamp      timestamptz       NOT NULL
, UNIQUE (payin, status)
);
CREATE TYPE payin_transfer_context AS ENUM ('personal-donation', 'team-donation');
CREATE TYPE payin_transfer_status AS ENUM ('pre', 'pending', 'failed', 'succeeded');
CREATE TABLE payin_transfers
( id            serial                   PRIMARY KEY
, ctime         timestamptz              NOT NULL DEFAULT CURRENT_TIMESTAMP
, remote_id     text
, payin         bigint                   NOT NULL REFERENCES payins
, payer         bigint                   NOT NULL REFERENCES participants
, recipient     bigint                   NOT NULL REFERENCES participants
, destination   bigint                   NOT NULL REFERENCES payment_accounts
, context       payin_transfer_context   NOT NULL
, status        payin_transfer_status    NOT NULL
, error         text
, amount        currency_amount          NOT NULL CHECK (amount > 0)
, unit_amount   currency_amount
, n_units       int
, period        donation_period
, team          bigint                   REFERENCES participants
, CONSTRAINT self_chk CHECK (payer <> recipient)
, CONSTRAINT team_chk CHECK ((context = 'team-donation') = (team IS NOT NULL))
, CONSTRAINT unit_chk CHECK ((unit_amount IS NULL) = (n_units IS NULL))
);
CREATE INDEX payin_transfers_payer_idx ON payin_transfers (payer);
CREATE INDEX payin_transfers_recipient_idx ON payin_transfers (recipient);
ALTER TABLE exchange_routes ADD COLUMN country text;
CREATE TYPE route_status AS ENUM ('pending', 'chargeable', 'consumed', 'failed', 'canceled');
ALTER TABLE exchange_routes ADD COLUMN status route_status;
UPDATE exchange_routes
       SET status = 'canceled'
     WHERE error = 'invalidated';
UPDATE exchange_routes
       SET status = 'chargeable'
     WHERE error IS NULL;
ALTER TABLE exchange_routes ALTER COLUMN status SET NOT NULL;
ALTER TABLE exchange_routes DROP COLUMN error;

-- migration #76
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'AUD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BGN';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BRL';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'CAD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'CHF';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'CNY';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'CZK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'DKK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'GBP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'HKD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'HRK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'HUF';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'IDR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'ILS';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'INR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'ISK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'JPY';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'KRW';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MXN';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MYR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'NOK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'NZD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'PHP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'PLN';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'RON';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'RUB';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'SEK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'SGD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'THB';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'TRY';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'ZAR';
CREATE OR REPLACE FUNCTION get_currency_exponent(currency) RETURNS int AS $$
    BEGIN RETURN (CASE
        WHEN $1 IN ('ISK', 'JPY', 'KRW') THEN 0 ELSE 2
    END); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OR REPLACE FUNCTION coalesce_currency_amount(currency_amount, currency) RETURNS currency_amount AS $$
    DECLARE
        c currency := COALESCE($1.currency, $2);
    BEGIN
        RETURN (COALESCE($1.amount, round(0, get_currency_exponent(c))), c);
    END;
$$ LANGUAGE plpgsql IMMUTABLE;
CREATE OR REPLACE FUNCTION round(currency_amount) RETURNS currency_amount AS $$
    BEGIN RETURN (round($1.amount, get_currency_exponent($1.currency)), $1.currency); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OR REPLACE FUNCTION zero(currency) RETURNS currency_amount AS $$
    BEGIN RETURN (round(0, get_currency_exponent($1)), $1); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OR REPLACE FUNCTION zero(currency_amount) RETURNS currency_amount AS $$
    BEGIN RETURN (round(0, get_currency_exponent($1.currency)), $1.currency); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OR REPLACE FUNCTION convert(currency_amount, currency, boolean) RETURNS currency_amount AS $$
    DECLARE
        rate numeric;
        result currency_amount;
    BEGIN
        IF ($1.currency = $2) THEN RETURN $1; END IF;
        IF ($1.currency = 'EUR' OR $2 = 'EUR') THEN
            rate := (
                SELECT r.rate
                  FROM currency_exchange_rates r
                 WHERE r.source_currency = $1.currency
                   AND r.target_currency = $2
            );
        ELSE
            rate := (
                SELECT r.rate
                  FROM currency_exchange_rates r
                 WHERE r.source_currency = $1.currency
                   AND r.target_currency = 'EUR'
            ) * (
                SELECT r.rate
                  FROM currency_exchange_rates r
                 WHERE r.source_currency = 'EUR'
                   AND r.target_currency = $2
            );
        END IF;
        IF (rate IS NULL) THEN
            RAISE 'missing exchange rate %->%', $1.currency, $2;
        END IF;
        result := ($1.amount * rate, $2);
        RETURN (CASE WHEN $3 THEN round(result) ELSE result END);
    END;
$$ LANGUAGE plpgsql STRICT;

-- migration #77
INSERT INTO app_conf VALUES
    ('check_email_domains', 'true'::jsonb);
INSERT INTO app_conf VALUES
    ('paypal_domain', '"sandbox.paypal.com"'::jsonb),
    ('paypal_id', '"ASTH9rn8IosjJcEwNYqV2KeHadB6O8MKVP7fL7kXeSuOml0ei77FRYU5E1thEF-1cT3Wp3Ibo0jXIbul"'::jsonb),
    ('paypal_secret', '"EAStyBaGBZk9MVBGrI_eb4O4iEVFPZcRoIsbKDwv28wxLzroLDKYwCnjZfr_jDoZyDB5epQVrjZraoFY"'::jsonb);
ALTER TABLE payment_accounts ALTER COLUMN charges_enabled DROP NOT NULL;
ALTER TYPE payment_net ADD VALUE IF NOT EXISTS 'paypal';
CREATE TABLE payin_transfer_events
( payin_transfer   int               NOT NULL REFERENCES payin_transfers
, status           payin_status      NOT NULL
, error            text
, timestamp        timestamptz       NOT NULL
, UNIQUE (payin_transfer, status)
);
ALTER TABLE payin_transfers ADD COLUMN fee currency_amount;
ALTER TABLE payins DROP CONSTRAINT success_chk;
ALTER TABLE participants ADD COLUMN payment_providers integer NOT NULL DEFAULT 0;
UPDATE participants SET payment_providers = 1 WHERE has_payment_account;
CREATE TYPE payment_providers AS ENUM ('stripe', 'paypal');
CREATE OR REPLACE FUNCTION update_payment_providers() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE participants
           SET payment_providers = coalesce((
                   SELECT sum(DISTINCT array_position(
                                           enum_range(NULL::payment_providers),
                                           a.provider::payment_providers
                                       ))
                     FROM payment_accounts a
                    WHERE ( a.participant = rec.participant OR
                            a.participant IN (
                                SELECT t.member
                                  FROM current_takes t
                                 WHERE t.team = rec.participant
                            )
                          )
                      AND a.is_current IS TRUE
                      AND a.verified IS TRUE
               ), 0)
         WHERE id = rec.participant
            OR id IN (
                   SELECT t.team FROM current_takes t WHERE t.member = rec.participant
               );
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER update_payment_providers
    AFTER INSERT OR UPDATE OR DELETE ON payment_accounts
    FOR EACH ROW EXECUTE PROCEDURE update_payment_providers();
ALTER TABLE payment_accounts ADD COLUMN verified boolean NOT NULL DEFAULT TRUE;
DROP TRIGGER update_has_payment_account ON payment_accounts;
DROP FUNCTION update_has_payment_account();
ALTER TABLE participants DROP COLUMN has_payment_account;
UPDATE payment_accounts SET id = id;
ALTER TABLE payment_accounts ALTER COLUMN verified DROP DEFAULT;

-- migration #78
CREATE OR REPLACE FUNCTION update_payment_accounts() RETURNS trigger AS $$
    BEGIN
        UPDATE payment_accounts
           SET verified = coalesce(NEW.verified, false)
         WHERE id = NEW.address
           AND participant = NEW.participant;
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER update_payment_accounts
    AFTER INSERT OR UPDATE ON emails
    FOR EACH ROW EXECUTE PROCEDURE update_payment_accounts();
UPDATE payment_accounts AS a
   SET verified = true
 WHERE verified IS NOT true
   AND ( SELECT e.verified
           FROM emails e
          WHERE e.address = a.id
            AND e.participant = a.participant
       ) IS true;

-- migration #79
ALTER TABLE takes ADD COLUMN paid_in_advance currency_amount;
ALTER TABLE takes ADD CONSTRAINT paid_in_advance_currency_chk CHECK (paid_in_advance::currency = amount::currency);
CREATE INDEX takes_team_idx ON takes (team);
DROP VIEW current_takes;
CREATE VIEW current_takes AS
    SELECT *
      FROM ( SELECT DISTINCT ON (team, member) t.*
               FROM takes t
           ORDER BY team, member, mtime DESC
           ) AS x
     WHERE amount IS NOT NULL;
UPDATE takes AS take
   SET paid_in_advance = coalesce_currency_amount((
           SELECT sum(tr.amount, take.amount::currency)
             FROM transfers tr
            WHERE tr.tippee = take.member
              AND tr.team = take.team
              AND tr.context = 'take-in-advance'
              AND tr.status = 'succeeded'
       ), take.amount::currency) + coalesce_currency_amount((
           SELECT sum(pt.amount, take.amount::currency)
             FROM payin_transfers pt
            WHERE pt.recipient = take.member
              AND pt.team = take.team
              AND pt.context = 'team-donation'
              AND pt.status = 'succeeded'
       ), take.amount::currency) - coalesce_currency_amount((
           SELECT sum(tr.amount, take.amount::currency)
             FROM transfers tr
            WHERE tr.tippee = take.member
              AND tr.team = take.team
              AND tr.context = 'take'
              AND tr.status = 'succeeded'
              AND tr.virtual IS TRUE
       ), take.amount::currency)
  FROM current_takes ct
 WHERE take.id = ct.id;

-- migration #80
CREATE TYPE blacklist_reason AS ENUM ('bounce', 'complaint');
CREATE TABLE email_blacklist
( address        text               NOT NULL
, ts             timestamptz        NOT NULL DEFAULT current_timestamp
, reason         blacklist_reason   NOT NULL
, details        text
, ses_data       jsonb
, ignore_after   timestamptz
, report_id      text
);
CREATE INDEX email_blacklist_idx ON email_blacklist (lower(address));
CREATE UNIQUE INDEX email_blacklist_report_key ON email_blacklist (report_id, address)
    WHERE report_id IS NOT NULL;
INSERT INTO app_conf VALUES
    ('fetch_email_bounces_every', '60'::jsonb),
    ('ses_feedback_queue_url', '""'::jsonb);
DROP INDEX queued_emails_idx;
CREATE UNIQUE INDEX queued_emails_idx ON notifications (id ASC)
    WHERE (email AND email_sent IS NULL);

-- migration #81
DROP INDEX email_blacklist_report_key;
CREATE UNIQUE INDEX email_blacklist_report_key ON email_blacklist (report_id, address);

-- migration #82
ALTER TYPE currency_basket ADD ATTRIBUTE amounts jsonb;
CREATE OR REPLACE FUNCTION empty_currency_basket() RETURNS currency_basket AS $$
    BEGIN RETURN (NULL::numeric,NULL::numeric,jsonb_build_object()); END;
$$ LANGUAGE plpgsql;
CREATE FUNCTION coalesce_currency_basket(currency_basket) RETURNS currency_basket AS $$
    BEGIN
        IF (coalesce($1.EUR, 0) > 0 OR coalesce($1.USD, 0) > 0) THEN
            IF ($1.amounts ? 'EUR' OR $1.amounts ? 'USD') THEN
                RAISE 'got an hybrid currency basket: %', $1;
            END IF;
            RETURN _wrap_amounts(
                jsonb_build_object('EUR', $1.EUR::text, 'USD', $1.USD::text)
            );
        ELSIF (jsonb_typeof($1.amounts) = 'object') THEN
            RETURN $1;
        ELSIF ($1.amounts IS NULL OR jsonb_typeof($1.amounts) <> 'null') THEN
            RETURN (NULL::numeric,NULL::numeric,jsonb_build_object());
        ELSE
            RAISE 'unexpected JSON type: %', jsonb_typeof($1.amounts);
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE;
CREATE OR REPLACE FUNCTION _wrap_amounts(jsonb) RETURNS currency_basket AS $$
    BEGIN
        IF ($1 IS NULL) THEN
            RETURN (NULL::numeric,NULL::numeric,jsonb_build_object());
        ELSE
            RETURN (NULL::numeric,NULL::numeric,$1);
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE;
CREATE OR REPLACE FUNCTION make_currency_basket(currency_amount) RETURNS currency_basket AS $$
    BEGIN RETURN (NULL::numeric,NULL::numeric,jsonb_build_object($1.currency::text, $1.amount::text)); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OR REPLACE FUNCTION currency_basket_add(currency_basket, currency_amount)
RETURNS currency_basket AS $$
    DECLARE
        r currency_basket;
    BEGIN
        r := coalesce_currency_basket($1);
        IF ($2.amount IS NULL OR $2.amount = 0 OR $2.currency IS NULL) THEN
            RETURN r;
        END IF;
        r.amounts := jsonb_set(
            r.amounts,
            string_to_array($2.currency::text, ' '),
            (coalesce((r.amounts->>$2.currency::text)::numeric, 0) + $2.amount)::text::jsonb
        );
        RETURN r;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OR REPLACE FUNCTION currency_basket_add(currency_basket, currency_basket)
RETURNS currency_basket AS $$
    DECLARE
        amounts1 jsonb;
        amounts2 jsonb;
        currency text;
    BEGIN
        amounts1 := (coalesce_currency_basket($1)).amounts;
        amounts2 := (coalesce_currency_basket($2)).amounts;
        FOR currency IN SELECT * FROM jsonb_object_keys(amounts2) LOOP
            amounts1 := jsonb_set(
                amounts1,
                string_to_array(currency, ' '),
                ( coalesce((amounts1->>currency)::numeric, 0) +
                  coalesce((amounts2->>currency)::numeric, 0)
                )::text::jsonb
            );
        END LOOP;
        RETURN _wrap_amounts(amounts1);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OR REPLACE FUNCTION currency_basket_sub(currency_basket, currency_amount)
RETURNS currency_basket AS $$
    BEGIN RETURN currency_basket_add($1, -$2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OR REPLACE FUNCTION currency_basket_sub(currency_basket, currency_basket)
RETURNS currency_basket AS $$
    DECLARE
        amounts1 jsonb;
        amounts2 jsonb;
        currency text;
    BEGIN
        amounts1 := (coalesce_currency_basket($1)).amounts;
        amounts2 := (coalesce_currency_basket($2)).amounts;
        FOR currency IN SELECT * FROM jsonb_object_keys(amounts2) LOOP
            amounts1 := jsonb_set(
                amounts1,
                string_to_array(currency, ' '),
                ( coalesce((amounts1->>currency)::numeric, 0) -
                  coalesce((amounts2->>currency)::numeric, 0)
                )::text::jsonb
            );
        END LOOP;
        RETURN _wrap_amounts(amounts1);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OR REPLACE FUNCTION currency_basket_contains(currency_basket, currency_amount)
RETURNS boolean AS $$
    BEGIN RETURN coalesce(coalesce_currency_basket($1)->$2.currency::text, 0) >= $2.amount; END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
DROP AGGREGATE basket_sum(currency_amount);
CREATE AGGREGATE basket_sum(currency_amount) (
    sfunc = currency_basket_add,
    stype = currency_basket,
    initcond = '(,,{})'
);
DROP AGGREGATE sum(currency_basket);
CREATE AGGREGATE sum(currency_basket) (
    sfunc = currency_basket_add,
    stype = currency_basket,
    initcond = '(,,{})'
);
CREATE FUNCTION get_amount_from_currency_basket(currency_basket, currency)
RETURNS numeric AS $$
    BEGIN RETURN (coalesce_currency_basket($1)).amounts->>$2::text; END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE FUNCTION get_amount_from_currency_basket(currency_basket, text)
RETURNS numeric AS $$
    BEGIN RETURN (coalesce_currency_basket($1)).amounts->>$2; END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR -> (
    leftarg = currency_basket,
    rightarg = currency,
    procedure = get_amount_from_currency_basket
);
CREATE OPERATOR -> (
    leftarg = currency_basket,
    rightarg = text,
    procedure = get_amount_from_currency_basket
);
ALTER TABLE paydays ALTER COLUMN transfer_volume           SET DEFAULT empty_currency_basket();
ALTER TABLE paydays ALTER COLUMN take_volume               SET DEFAULT empty_currency_basket();
ALTER TABLE paydays ALTER COLUMN week_deposits             SET DEFAULT empty_currency_basket();
ALTER TABLE paydays ALTER COLUMN week_withdrawals          SET DEFAULT empty_currency_basket();
ALTER TABLE paydays ALTER COLUMN transfer_volume_refunded  SET DEFAULT empty_currency_basket();
ALTER TABLE paydays ALTER COLUMN week_deposits_refunded    SET DEFAULT empty_currency_basket();
ALTER TABLE paydays ALTER COLUMN week_withdrawals_refunded SET DEFAULT empty_currency_basket();
UPDATE participants
   SET accepted_currencies = NULL
 WHERE status = 'stub'
   AND accepted_currencies IS NOT NULL;

-- migration #83
ALTER TABLE emails DROP CONSTRAINT emails_participant_address_key;
CREATE UNIQUE INDEX emails_participant_address_key ON emails (participant, lower(address));

-- migration #84
UPDATE elsewhere
   SET extra_info = (
           extra_info::jsonb - 'events_url' - 'followers_url' - 'following_url'
           - 'gists_url' - 'html_url' - 'organizations_url' - 'received_events_url'
           - 'repos_url' - 'starred_url' - 'subscriptions_url'
       )::json
 WHERE platform = 'github'
   AND json_typeof(extra_info) = 'object';
UPDATE elsewhere
   SET extra_info = (extra_info::jsonb - 'id_str' - 'entities' - 'status')::json
 WHERE platform = 'twitter'
   AND json_typeof(extra_info) = 'object';

-- migration #85
CREATE OR REPLACE FUNCTION update_payment_providers() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE participants
           SET payment_providers = coalesce((
                   SELECT sum(DISTINCT array_position(
                                           enum_range(NULL::payment_providers),
                                           a.provider::payment_providers
                                       ))
                     FROM payment_accounts a
                    WHERE ( a.participant = rec.participant OR
                            a.participant IN (
                                SELECT t.member
                                  FROM current_takes t
                                 WHERE t.team = rec.participant
                            )
                          )
                      AND a.is_current IS TRUE
                      AND a.verified IS TRUE
                      AND coalesce(a.charges_enabled, true)
               ), 0)
         WHERE id = rec.participant
            OR id IN (
                   SELECT t.team FROM current_takes t WHERE t.member = rec.participant
               );
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;
UPDATE participants AS p
   SET payment_providers = coalesce((
           SELECT sum(DISTINCT array_position(
                                   enum_range(NULL::payment_providers),
                                   a.provider::payment_providers
                               ))
             FROM payment_accounts a
            WHERE ( a.participant = p.id OR
                    a.participant IN (
                        SELECT t.member
                          FROM current_takes t
                         WHERE t.team = p.id
                    )
                  )
              AND a.is_current IS TRUE
              AND a.verified IS TRUE
              AND coalesce(a.charges_enabled, true)
       ), 0)
 WHERE EXISTS (
           SELECT a.id
             FROM payment_accounts a
            WHERE a.participant = p.id
              AND a.charges_enabled IS false
       );

-- migration #86
CREATE OR REPLACE FUNCTION currency_amount_fuzzy_sum_sfunc(
    currency_amount, currency_amount, currency
) RETURNS currency_amount AS $$
    BEGIN
        IF ($2.amount IS NULL OR $2.currency IS NULL) THEN RETURN $1; END IF;
        RETURN ($1.amount + (convert($2, $3, false)).amount, $3);
    END;
$$ LANGUAGE plpgsql STRICT;
CREATE OR REPLACE FUNCTION currency_amount_fuzzy_sum_ffunc(currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.amount IS NULL OR $1.currency IS NULL) THEN RETURN NULL; END IF;
        RETURN round($1);
    END;
$$ LANGUAGE plpgsql;
DROP AGGREGATE sum(currency_amount, currency);
CREATE AGGREGATE sum(currency_amount, currency) (
    sfunc = currency_amount_fuzzy_sum_sfunc,
    finalfunc = currency_amount_fuzzy_sum_ffunc,
    stype = currency_amount,
    initcond = '(0,)'
);
UPDATE tips
   SET paid_in_advance = NULL
 WHERE paid_in_advance IS NOT NULL
   AND (paid_in_advance).amount IS NULL;

-- migration #87
ALTER TABLE tips ADD COLUMN renewal_mode int NOT NULL DEFAULT 1;
DROP VIEW current_tips;
CREATE VIEW current_tips AS
    SELECT DISTINCT ON (tipper, tippee) *
      FROM tips
  ORDER BY tipper, tippee, mtime DESC;
CREATE FUNCTION get_previous_tip(t tips) RETURNS tips AS $$
    SELECT old_t.*
      FROM tips old_t
     WHERE old_t.tipper = t.tipper
       AND old_t.tippee = t.tippee
       AND old_t.mtime < t.mtime
  ORDER BY old_t.mtime DESC
     LIMIT 1;
$$ LANGUAGE SQL STRICT STABLE;
DELETE FROM tips AS t
 WHERE t.periodic_amount = 0
   AND get_previous_tip(t) IS NULL;
DELETE FROM tips AS t
 WHERE t.amount = (get_previous_tip(t)).amount
   AND t.period = (get_previous_tip(t)).period
   AND t.periodic_amount = (get_previous_tip(t)).periodic_amount
   AND t.paid_in_advance = (get_previous_tip(t)).paid_in_advance;
UPDATE tips AS t
   SET amount = (get_previous_tip(t)).amount
     , periodic_amount = (get_previous_tip(t)).periodic_amount
     , period = (get_previous_tip(t)).period
     , paid_in_advance = (get_previous_tip(t)).paid_in_advance
     , renewal_mode = 0
 WHERE t.amount = 0;
DROP FUNCTION get_previous_tip(tips);
ALTER TABLE tips ADD CONSTRAINT tips_periodic_amount_check CHECK (periodic_amount > 0);

-- migration #88
UPDATE participants
   SET goal = (-1,main_currency)::currency_amount
 WHERE status = 'closed';

-- migration #89
CREATE FUNCTION compute_payment_providers(bigint) RETURNS bigint AS $$
    SELECT coalesce((
        SELECT sum(DISTINCT array_position(
                                enum_range(NULL::payment_providers),
                                a.provider::payment_providers
                            ))
          FROM payment_accounts a
         WHERE ( a.participant = $1 OR
                 a.participant IN (
                     SELECT t.member
                       FROM current_takes t
                      WHERE t.team = $1
                 )
               )
           AND a.is_current IS TRUE
           AND a.verified IS TRUE
           AND coalesce(a.charges_enabled, true)
    ), 0);
$$ LANGUAGE SQL STRICT;
CREATE FUNCTION update_team_payment_providers() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE participants
           SET payment_providers = compute_payment_providers(rec.team)
         WHERE id = rec.team;
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER update_team_payment_providers
    AFTER INSERT OR DELETE ON takes
    FOR EACH ROW EXECUTE PROCEDURE update_team_payment_providers();
CREATE OR REPLACE FUNCTION update_payment_providers() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE participants
           SET payment_providers = compute_payment_providers(rec.participant)
         WHERE id = rec.participant
            OR id IN (
                   SELECT t.team FROM current_takes t WHERE t.member = rec.participant
               );
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;
UPDATE participants
   SET payment_providers = compute_payment_providers(id)
 WHERE kind = 'group'
   AND payment_providers <> compute_payment_providers(id);

-- migration #90
CREATE OR REPLACE FUNCTION update_community_nmembers() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE communities
           SET nmembers = (
                   SELECT count(*)
                     FROM community_memberships m
                    WHERE m.community = rec.community
                      AND m.is_on
               )
         WHERE id = rec.community;
        RETURN rec;
    END;
$$ LANGUAGE plpgsql;
CREATE OR REPLACE FUNCTION update_nsubscribers() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE participants
           SET nsubscribers = (
                   SELECT count(*)
                     FROM subscriptions s
                    WHERE s.publisher = rec.publisher
                      AND s.is_on
               )
         WHERE id = rec.publisher;
        RETURN rec;
    END;
$$ LANGUAGE plpgsql;
DROP TRIGGER update_community_nmembers ON community_memberships;
CREATE TRIGGER update_community_nmembers
    AFTER INSERT OR UPDATE OR DELETE ON community_memberships
    FOR EACH ROW
    EXECUTE PROCEDURE update_community_nmembers();
DROP TRIGGER update_nsubscribers ON subscriptions;
CREATE TRIGGER update_nsubscribers
    AFTER INSERT OR UPDATE OR DELETE ON subscriptions
    FOR EACH ROW
    EXECUTE PROCEDURE update_nsubscribers();
UPDATE communities AS c
   SET nmembers = (
           SELECT count(*)
             FROM community_memberships m
            WHERE m.community = c.id
              AND m.is_on
       );
UPDATE participants AS p
   SET nsubscribers = (
           SELECT count(*)
             FROM subscriptions s
            WHERE s.publisher = p.id
              AND s.is_on
       );

-- migration #91
ALTER TYPE payment_net ADD VALUE IF NOT EXISTS 'stripe-sdd';
UPDATE participants
   SET email_notif_bits = email_notif_bits | 64 | 128 | 256 | 512 | 1024
 WHERE email_notif_bits <> (email_notif_bits | 64 | 128 | 256 | 512 | 1024);

-- migration #92
ALTER TABLE paydays ADD COLUMN week_payins currency_basket;
UPDATE paydays AS payday
   SET week_payins = (
           SELECT basket_sum(pi.amount)
             FROM payins pi
            WHERE pi.ctime >= (
                      SELECT previous_payday.ts_start
                        FROM paydays previous_payday
                       WHERE previous_payday.id = payday.id - 1
                  )
              AND pi.ctime < payday.ts_start
              AND pi.status = 'succeeded'
       )
 WHERE id >= 132;

-- migration #93
CREATE TYPE encryption_scheme AS ENUM ('fernet');
CREATE TYPE encrypted AS (
    scheme encryption_scheme, payload bytea, ts timestamptz
);
CREATE TABLE identities
( id               bigserial     PRIMARY KEY
, ctime            timestamptz   NOT NULL DEFAULT current_timestamp
, participant      bigint        NOT NULL REFERENCES participants
, info             encrypted     NOT NULL
);
CREATE UNIQUE INDEX ON identities (participant, ctime DESC);

-- migration #94
ALTER TABLE takes
    DROP CONSTRAINT not_negative,
    ADD CONSTRAINT amount_chk CHECK (amount IS NULL OR amount >= 0 OR (amount).amount = -1),
    ALTER COLUMN amount DROP DEFAULT;
UPDATE takes AS t
   SET amount = (-1,amount::currency)::currency_amount
     , mtime = current_timestamp
  FROM ( SELECT t2.id
           FROM current_takes t2
          WHERE t2.mtime = t2.ctime
       ) t2
 WHERE t.id = t2.id;

-- migration #95
ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'indirect-payout';

-- migration #96
ALTER TABLE notifications ADD COLUMN idem_key text;
INSERT INTO app_conf (key, value) VALUES
    ('cron_intervals', jsonb_build_object(
        'check_db', (SELECT value::text::int FROM app_conf WHERE key = 'check_db_every'),
        'clean_up_counters', (SELECT value::text::int FROM app_conf WHERE key = 'clean_up_counters_every'),
        'dequeue_emails', (SELECT value::text::int FROM app_conf WHERE key = 'dequeue_emails_every'),
        'fetch_email_bounces', (SELECT value::text::int FROM app_conf WHERE key = 'fetch_email_bounces_every'),
        'notify_patrons', 120,
        'refetch_elsewhere_data', (SELECT value::text::int FROM app_conf WHERE key = 'refetch_elsewhere_data_every'),
        'refetch_repos', (SELECT value::text::int FROM app_conf WHERE key = 'refetch_repos_every'),
        'send_newsletters', (SELECT value::text::int FROM app_conf WHERE key = 'send_newsletters_every')
    ))
    ON CONFLICT (key) DO UPDATE SET value = excluded.value;
DELETE FROM app_conf WHERE key IN (
    'check_db_every', 'clean_up_counters_every', 'dequeue_emails_every',
    'fetch_email_bounces_every', 'refetch_elsewhere_data_every',
    'refetch_repos_every', 'send_newsletters_every'
);

-- migration #97
CREATE UNIQUE INDEX ON notifications (participant, event, idem_key);

-- migration #98
ALTER TABLE notifications ADD COLUMN context_is_cbor boolean;

-- migration #99
ALTER TABLE notifications DROP COLUMN context_is_cbor;

-- migration #100
CREATE OR REPLACE FUNCTION compute_payment_providers(bigint) RETURNS bigint AS $$
    SELECT coalesce((
        SELECT sum(DISTINCT array_position(
                                enum_range(NULL::payment_providers),
                                a.provider::payment_providers
                            ))
          FROM payment_accounts a
         WHERE ( a.participant = $1 OR
                 a.participant IN (
                     SELECT t.member
                       FROM current_takes t
                      WHERE t.team = $1
                        AND t.amount <> 0
                 )
               )
           AND a.is_current IS TRUE
           AND a.verified IS TRUE
           AND coalesce(a.charges_enabled, true)
    ), 0);
$$ LANGUAGE SQL STRICT;
UPDATE participants SET payment_providers = compute_payment_providers(id) WHERE kind = 'group';

-- migration #101
CREATE INDEX events_admin_idx ON events (ts DESC) WHERE type = 'admin_request';

-- migration #102
ALTER TYPE payin_status ADD VALUE IF NOT EXISTS 'awaiting_payer_action';
ALTER TABLE payins ADD COLUMN intent_id text;

-- migration #103
ALTER TABLE emails ALTER COLUMN participant DROP NOT NULL;
ALTER TABLE emails
    ADD COLUMN disavowed boolean,
    ADD COLUMN disavowed_time timestamptz;
ALTER TABLE emails
    ADD CONSTRAINT not_verified_and_disavowed CHECK (NOT (verified AND disavowed));

-- migration #104
WITH pending_paypal_payins AS (
    SELECT pi.id
      FROM payins pi
      JOIN exchange_routes r ON r.id = pi.route
     WHERE r.network = 'paypal'
       AND pi.status = 'pending'
)
UPDATE payins
   SET status = 'awaiting_payer_action'
 WHERE id IN (SELECT * FROM pending_paypal_payins);

-- migration #105
INSERT INTO app_conf (key, value) VALUES ('check_avatar_urls', 'true'::jsonb);

-- migration #106
CREATE TYPE refund_reason AS ENUM ('duplicate', 'fraud', 'requested_by_payer');
CREATE TYPE refund_status AS ENUM ('pre', 'pending', 'failed', 'succeeded');
CREATE TABLE payin_refunds
( id               bigserial             PRIMARY KEY
, ctime            timestamptz           NOT NULL DEFAULT current_timestamp
, payin            bigint                NOT NULL REFERENCES payins
, remote_id        text
, amount           currency_amount       NOT NULL CHECK (amount > 0)
, reason           refund_reason         NOT NULL
, description      text
, status           refund_status         NOT NULL
, error            text
, UNIQUE (payin, remote_id)
);
CREATE TABLE payin_transfer_reversals
( id               bigserial             PRIMARY KEY
, ctime            timestamptz           NOT NULL DEFAULT current_timestamp
, payin_transfer   bigint                NOT NULL REFERENCES payin_transfers
, remote_id        text
, payin_refund     bigint                REFERENCES payin_refunds
, amount           currency_amount       NOT NULL CHECK (amount > 0)
, UNIQUE (payin_transfer, remote_id)
);
ALTER TABLE payins
    ADD COLUMN refunded_amount currency_amount CHECK (NOT (refunded_amount <= 0));
ALTER TABLE payin_transfers
    ADD COLUMN reversed_amount currency_amount CHECK (NOT (reversed_amount <= 0));
ALTER TABLE payins
    ADD CONSTRAINT refund_currency_chk CHECK (refunded_amount::currency = amount::currency);
ALTER TABLE payin_transfers
    ADD CONSTRAINT reversal_currency_chk CHECK (reversed_amount::currency = amount::currency);

-- migration #107
ALTER TABLE payin_refunds ALTER COLUMN reason DROP NOT NULL;

-- migration #108
UPDATE emails SET verified = null WHERE participant IS null AND verified IS true;

-- migration #109
CREATE OR REPLACE FUNCTION update_payment_providers() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE participants
           SET payment_providers = compute_payment_providers(id)
         WHERE id = rec.participant
            OR id IN (
                   SELECT t.team FROM current_takes t WHERE t.member = rec.participant
               );
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;
UPDATE participants
   SET payment_providers = compute_payment_providers(id)
 WHERE kind = 'group'
   AND payment_providers <> compute_payment_providers(id);

-- migration #110
DELETE FROM notifications WHERE event = 'identity_required';

-- migration #111
CREATE FUNCTION currency_amount_mul(numeric, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        RETURN ($2.amount * $1, $2.currency);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR * (
    leftarg = numeric,
    rightarg = currency_amount,
    procedure = currency_amount_mul,
    commutator = *
);
CREATE FUNCTION currency_amount_div(currency_amount, currency_amount)
RETURNS numeric AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN $1.amount / $2.amount;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OPERATOR / (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_div
);

-- migration #112
UPDATE email_blacklist
   SET ignore_after = ts + interval '5 days'
 WHERE ignore_after IS NULL
   AND ses_data->'bounce'->>'bounceType' = 'Transient';

-- migration #113
ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'tip-in-arrears';
ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'take-in-arrears';
CREATE CAST (current_tips AS tips) WITH INOUT;
CREATE FUNCTION compute_arrears(tip tips) RETURNS currency_amount AS $$
    SELECT coalesce_currency_amount((
               SELECT sum(tip_at_the_time.amount, tip.amount::currency)
                 FROM paydays payday
                 JOIN LATERAL (
                          SELECT tip2.*
                            FROM tips tip2
                           WHERE tip2.tipper = tip.tipper
                             AND tip2.tippee = tip.tippee
                             AND tip2.mtime < payday.ts_start
                        ORDER BY tip2.mtime DESC
                           LIMIT 1
                      ) tip_at_the_time ON true
                WHERE payday.ts_start > tip.ctime
                  AND payday.ts_start > '2018-08-15'
                  AND payday.ts_end > payday.ts_start
                  AND NOT EXISTS (
                          SELECT 1
                            FROM transfers tr
                           WHERE tr.tipper = tip.tipper
                             AND coalesce(tr.team, tr.tippee) = tip.tippee
                             AND tr.context IN ('tip', 'take')
                             AND tr.timestamp >= payday.ts_start
                             AND tr.timestamp <= payday.ts_end
                             AND tr.status = 'succeeded'
                      )
           ), tip.amount::currency) - coalesce_currency_amount((
               SELECT sum(tr.amount, tip.amount::currency)
                 FROM transfers tr
                WHERE tr.tipper = tip.tipper
                  AND coalesce(tr.team, tr.tippee) = tip.tippee
                  AND tr.context IN ('tip-in-arrears', 'take-in-arrears')
                  AND tr.status = 'succeeded'
           ), tip.amount::currency);
$$ LANGUAGE sql;
CREATE FUNCTION compute_arrears(tip current_tips) RETURNS currency_amount AS $$
    SELECT compute_arrears(tip::tips);
$$ LANGUAGE sql;

-- migration #114
ALTER TABLE exchange_routes DROP CONSTRAINT currency_chk;
ALTER TABLE exchange_routes ADD COLUMN is_default boolean;
CREATE UNIQUE INDEX exchange_routes_is_default_key ON exchange_routes (participant, is_default) WHERE is_default IS TRUE;

-- migration #115
CREATE TABLE scheduled_payins
( id               bigserial         PRIMARY KEY
, ctime            timestamptz       NOT NULL DEFAULT current_timestamp
, mtime            timestamptz       NOT NULL DEFAULT current_timestamp
, execution_date   date              NOT NULL
, payer            bigint            NOT NULL REFERENCES participants
, amount           currency_amount   CHECK (amount IS NULL OR amount > 0)
, transfers        json              NOT NULL
, automatic        boolean           NOT NULL DEFAULT FALSE
, notifs_count     int               NOT NULL DEFAULT 0
, last_notif_ts    timestamptz
, customized       boolean
, payin            bigint            REFERENCES payins
, CONSTRAINT amount_is_null_when_not_automatic CHECK ((amount IS NULL) = (NOT automatic))
, CONSTRAINT notifs CHECK ((notifs_count = 0) = (last_notif_ts IS NULL))
);
CREATE INDEX scheduled_payins_payer_idx ON scheduled_payins (payer);
ALTER TABLE payins ADD COLUMN off_session boolean NOT NULL DEFAULT FALSE;
ALTER TABLE payins ALTER COLUMN off_session DROP DEFAULT;

-- migration #116
UPDATE scheduled_payins
   SET execution_date = '2020-02-14'
 WHERE execution_date < '2020-02-14'::date
   AND automatic IS TRUE
   AND payin IS NULL;
UPDATE scheduled_payins
   SET execution_date = (SELECT pi.ctime::date FROM payins pi WHERE pi.id = payin)
 WHERE execution_date < '2020-02-14'::date
   AND automatic IS TRUE
   AND payin IS NOT NULL;

-- migration #117
ALTER TABLE notifications ADD COLUMN hidden_since timestamptz;

-- migration #118
ALTER TABLE email_blacklist ADD COLUMN ignored_by bigint REFERENCES participants;
UPDATE email_blacklist AS bl
   SET ignore_after = current_timestamp
     , ignored_by = e.participant
  FROM emails e
 WHERE lower(e.address) = lower(bl.address)
   AND e.verified
   AND (bl.ignore_after IS NULL OR bl.ignore_after > current_timestamp)
   AND (bl.reason = 'bounce' AND bl.ts < (e.added_time + interval '24 hours') OR
        bl.reason = 'complaint' AND bl.details = 'disavowed');

-- migration #119
ALTER TYPE blacklist_reason ADD VALUE IF NOT EXISTS 'throwaway';
ALTER TYPE blacklist_reason ADD VALUE IF NOT EXISTS 'other';
ALTER TABLE email_blacklist ADD COLUMN added_by bigint REFERENCES participants;

-- migration #120
DROP TRIGGER search_vector_update ON statements;
DROP INDEX IF EXISTS statements_fts_idx;
ALTER TABLE statements
        ALTER COLUMN search_conf SET DATA TYPE text USING (search_conf::text),
        DROP COLUMN search_vector;
CREATE FUNCTION to_tsvector(text, text) RETURNS tsvector AS $$
        SELECT to_tsvector($1::regconfig, $2);
    $$ LANGUAGE sql STRICT IMMUTABLE;
CREATE INDEX statements_fts_idx ON statements USING GIN (to_tsvector(search_conf, content));

-- migration #121
CREATE INDEX repositories_participant_idx ON repositories (participant, show_on_profile);
CREATE INDEX repositories_info_fetched_at_idx ON repositories (info_fetched_at ASC)
    WHERE participant IS NOT NULL AND show_on_profile;

-- migration #122
CREATE INDEX elsewhere_info_fetched_at_idx ON elsewhere (info_fetched_at ASC);
CREATE INDEX takes_member_idx ON takes (member);

-- migration #123
ALTER TABLE payin_transfer_events
    ALTER COLUMN status TYPE payin_transfer_status USING status::text::payin_transfer_status;
WITH updated AS (
    UPDATE payin_transfers pt
       SET status = 'pending'
      FROM payins pi
     WHERE pi.id = pt.payin
       AND pi.status = 'pending'
       AND pt.status = 'pre'
 RETURNING pt.*
)
INSERT INTO payin_transfer_events
            (payin_transfer, status, error, timestamp)
     SELECT pt.id, pt.status, pt.error, current_timestamp
       FROM updated pt;

-- migration #124
CREATE FUNCTION update_pending_notifs() RETURNS trigger AS $$
    DECLARE
        rec record;
    BEGIN
        rec := (CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
        UPDATE participants
           SET pending_notifs = (
                   SELECT count(*)
                     FROM notifications
                    WHERE participant = rec.participant
                      AND web
                      AND is_new
               )
         WHERE id = rec.participant;
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER update_pending_notifs
    AFTER INSERT OR UPDATE OF is_new, web OR DELETE ON notifications
    FOR EACH ROW EXECUTE PROCEDURE update_pending_notifs();

-- migration #125
ALTER TABLE tips ADD COLUMN hidden boolean;
CREATE OR REPLACE VIEW current_tips AS
    SELECT DISTINCT ON (tipper, tippee) *
      FROM tips
  ORDER BY tipper, tippee, mtime DESC;

-- migration #126
INSERT INTO app_conf VALUES ('check_email_servers', 'true'::jsonb);

-- migration #127
ALTER TABLE elsewhere ADD COLUMN missing_since timestamptz;

-- migration #128
ALTER TABLE elsewhere DROP CONSTRAINT elsewhere_participant_platform_key;
CREATE INDEX elsewhere_participant_platform_idx ON elsewhere (participant, platform);

-- migration #129
CREATE TYPE email_status AS ENUM ('queued', 'skipped', 'sending', 'sent', 'failed');
ALTER TABLE notifications ADD COLUMN email_status email_status;
UPDATE notifications
   SET email_status = (CASE
           WHEN email_sent = true THEN 'sent'
           WHEN email_sent = false THEN 'skipped'
           WHEN email = true THEN 'queued'
           ELSE null
       END)::email_status
 WHERE email_sent IS NOT null OR email IS true;
DROP INDEX queued_emails_idx;
CREATE UNIQUE INDEX queued_emails_idx ON notifications (id ASC)
    WHERE (email AND email_status = 'queued');
ALTER TABLE notifications DROP COLUMN email_sent;
ALTER TABLE notifications ADD CONSTRAINT email_chk CHECK (email = (email_status IS NOT null));

-- migration #130
CREATE OR REPLACE FUNCTION decrement_rate_limit(key text, cap int, period float) RETURNS int AS $$
    UPDATE rate_limiting AS r
       SET counter = greatest(r.counter - 1 - compute_leak(cap, period, r.ts), 0)
              , ts = current_timestamp
     WHERE r.key = key
 RETURNING counter;
$$ LANGUAGE sql;

-- migration #131
DROP FUNCTION decrement_rate_limit(text, int, float);
CREATE FUNCTION decrement_rate_limit(a_key text, cap int, period float) RETURNS int AS $$
    WITH updated AS (
             UPDATE rate_limiting AS r
                SET counter = greatest(r.counter - 1 - compute_leak(cap, period, r.ts), 0)
                  , ts = current_timestamp
              WHERE r.key = a_key
          RETURNING counter
         ),
         deleted AS (
             DELETE FROM rate_limiting AS r
              WHERE r.key = a_key
                AND r.counter = 0
         )
    SELECT counter FROM updated;
$$ LANGUAGE sql;
DELETE FROM rate_limiting WHERE counter = 0;

-- migration #132
ALTER TABLE payment_accounts ADD COLUMN authorized boolean;

-- migration #133
UPDATE participants
   SET avatar_url = 'https://nitter.net/pic/' || regexp_replace(substr(avatar_url, 23), '/', '%2F', 'g')
 WHERE avatar_url LIKE 'https://pbs.twimg.com/%';

-- migration #134
DELETE FROM app_conf WHERE key LIKE 'bountysource_%';

-- migration #135
UPDATE scheduled_payins
   SET execution_date = execution_date - interval '1 day'
 WHERE payin IS null
   AND execution_date > current_date
   AND last_notif_ts IS null
   AND automatic IS true;

-- migration #136
CREATE OR REPLACE FUNCTION compute_arrears(tip tips) RETURNS currency_amount AS $$
    SELECT coalesce_currency_amount((
               SELECT sum(tip_at_the_time.amount, tip.amount::currency)
                 FROM paydays payday
                 JOIN LATERAL (
                          SELECT tip2.*
                            FROM tips tip2
                           WHERE tip2.tipper = tip.tipper
                             AND tip2.tippee = tip.tippee
                             AND tip2.mtime < payday.ts_start
                        ORDER BY tip2.mtime DESC
                           LIMIT 1
                      ) tip_at_the_time ON true
                WHERE payday.ts_start > tip.ctime
                  AND payday.ts_start > '2018-08-15'
                  AND payday.ts_end > payday.ts_start
                  AND tip_at_the_time.renewal_mode > 0
                  AND NOT EXISTS (
                          SELECT 1
                            FROM transfers tr
                           WHERE tr.tipper = tip.tipper
                             AND coalesce(tr.team, tr.tippee) = tip.tippee
                             AND tr.context IN ('tip', 'take')
                             AND tr.timestamp >= payday.ts_start
                             AND tr.timestamp <= payday.ts_end
                             AND tr.status = 'succeeded'
                      )
           ), tip.amount::currency) - coalesce_currency_amount((
               SELECT sum(tr.amount, tip.amount::currency)
                 FROM transfers tr
                WHERE tr.tipper = tip.tipper
                  AND coalesce(tr.team, tr.tippee) = tip.tippee
                  AND tr.context IN ('tip-in-arrears', 'take-in-arrears')
                  AND tr.status = 'succeeded'
           ), tip.amount::currency);
$$ LANGUAGE sql;

-- migration #137
DROP INDEX username_trgm_idx;
CREATE INDEX username_trgm_idx ON participants
    USING GIN (lower(username) gin_trgm_ops)
    WHERE status = 'active'
      AND NOT username like '~%';
DROP INDEX community_trgm_idx;
CREATE INDEX community_trgm_idx ON communities
    USING GIN (lower(name) gin_trgm_ops);
DROP INDEX repositories_trgm_idx;
CREATE INDEX repositories_trgm_idx ON repositories
    USING GIN (lower(name) gin_trgm_ops)
    WHERE participant IS NOT NULL;

-- migration #138
CREATE INDEX scheduled_payins_payin_idx ON scheduled_payins (payin);
UPDATE scheduled_payins AS sp
   SET payin = coalesce((
           SELECT pi2.id
             FROM payins pi2
            WHERE pi2.payer = pi.payer
              AND pi2.id > pi.id
              AND pi2.ctime < (pi.ctime + interval '5 minutes')
              AND pi2.amount = pi.amount
              AND pi2.off_session = pi.off_session
              AND pi2.status IN ('pending', 'succeeded')
              AND NOT EXISTS (
                      SELECT 1
                        FROM scheduled_payins sp2
                       WHERE sp2.payin = pi2.id
                  )
         ORDER BY pi2.id
            LIMIT 1
       ), payin)
  FROM payins pi
 WHERE pi.id = sp.payin
   AND pi.status = 'failed'
   AND pi.error LIKE 'For ''sepa_debit'' payments, we currently require %';

-- migration #139
ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'leftover-take';
ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'partial-tip';

-- migration #140
ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'partial-take';
CREATE OR REPLACE FUNCTION empty_currency_basket() RETURNS currency_basket AS $$
    BEGIN RETURN (0::numeric,0::numeric,jsonb_build_object()); END;
$$ LANGUAGE plpgsql;
CREATE OR REPLACE FUNCTION coalesce_currency_basket(currency_basket) RETURNS currency_basket AS $$
    BEGIN
        IF ($1 IS NULL) THEN
            RETURN empty_currency_basket();
        END IF;
        IF (coalesce($1.EUR, 0) <> 0 OR coalesce($1.USD, 0) <> 0) THEN
            IF (jsonb_typeof($1.amounts) = 'object') THEN
                RAISE 'got an hybrid currency basket: %', $1;
            END IF;
            RETURN _wrap_amounts(jsonb_build_object(
                'EUR', coalesce($1.EUR, 0)::text,
                'USD', coalesce($1.USD, 0)::text
            ));
        ELSIF (jsonb_typeof($1.amounts) = 'object') THEN
            IF ($1.EUR IS NULL OR $1.USD IS NULL) THEN
                RETURN (0::numeric,0::numeric,$1.amounts);
            END IF;
            RETURN $1;
        ELSIF ($1.amounts IS NULL OR jsonb_typeof($1.amounts) <> 'null') THEN
            RETURN (0::numeric,0::numeric,jsonb_build_object());
        ELSE
            RAISE 'unexpected JSON type: %', jsonb_typeof($1.amounts);
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE;
CREATE OR REPLACE FUNCTION _wrap_amounts(jsonb) RETURNS currency_basket AS $$
    BEGIN
        IF ($1 IS NULL) THEN
            RETURN (0::numeric,0::numeric,jsonb_build_object());
        ELSE
            RETURN (0::numeric,0::numeric,$1);
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE;
CREATE OR REPLACE FUNCTION make_currency_basket(currency_amount) RETURNS currency_basket AS $$
    BEGIN RETURN (0::numeric,0::numeric,jsonb_build_object($1.currency::text, $1.amount::text)); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

-- migration #141
CREATE OR REPLACE FUNCTION compute_arrears(tip tips) RETURNS currency_amount AS $$
    SELECT coalesce_currency_amount((
               SELECT sum(tip_at_the_time.amount, tip.amount::currency)
                 FROM paydays payday
                 JOIN LATERAL (
                          SELECT tip2.*
                            FROM tips tip2
                           WHERE tip2.tipper = tip.tipper
                             AND tip2.tippee = tip.tippee
                             AND tip2.mtime < payday.ts_start
                        ORDER BY tip2.mtime DESC
                           LIMIT 1
                      ) tip_at_the_time ON true
                WHERE payday.ts_start > tip.ctime
                  AND payday.ts_start > '2018-08-15'
                  AND payday.ts_end > payday.ts_start
                  AND tip_at_the_time.renewal_mode > 0
                  AND NOT EXISTS (
                          SELECT 1
                            FROM transfers tr
                           WHERE tr.tipper = tip.tipper
                             AND coalesce(tr.team, tr.tippee) = tip.tippee
                             AND tr.context IN ('tip', 'take')
                             AND tr.timestamp >= payday.ts_start
                             AND tr.timestamp <= payday.ts_end
                             AND tr.status = 'succeeded'
                      )
           ), tip.amount::currency) - coalesce_currency_amount((
               SELECT sum(tr.amount, tip.amount::currency)
                 FROM transfers tr
                WHERE tr.tipper = tip.tipper
                  AND coalesce(tr.team, tr.tippee) = tip.tippee
                  AND tr.context IN (
                          'tip-in-arrears', 'take-in-arrears',
                          'partial-tip', 'partial-take'
                      )
                  AND tr.status = 'succeeded'
           ), tip.amount::currency);
$$ LANGUAGE sql;

-- migration #142
ALTER TABLE payin_transfers DROP CONSTRAINT IF EXISTS payin_transfers_reversed_amount_check;
ALTER TABLE payin_transfers ADD CONSTRAINT payin_transfers_reversed_amount_check CHECK (NOT (reversed_amount < 0));

-- migration #143
ALTER TABLE participants
    ADD COLUMN is_controversial boolean,
    ADD COLUMN is_spam boolean;
CREATE FUNCTION update_profile_visibility() RETURNS trigger AS $$
    BEGIN
        IF (NEW.is_controversial OR NEW.is_spam OR NEW.is_suspended) THEN
            NEW.profile_noindex = NEW.profile_noindex | 2;
            NEW.hide_from_lists = NEW.hide_from_lists | 2;
            NEW.hide_from_search = NEW.hide_from_search | 2;
        ELSIF (NEW.is_controversial IS false) THEN
            NEW.profile_noindex = NEW.profile_noindex & 2147483645;
            NEW.hide_from_lists = NEW.hide_from_lists & 2147483645;
            NEW.hide_from_search = NEW.hide_from_search & 2147483645;
        ELSE
            NEW.profile_noindex = NEW.profile_noindex | 2;
            NEW.hide_from_lists = NEW.hide_from_lists & 2147483645;
            NEW.hide_from_search = NEW.hide_from_search & 2147483645;
        END IF;
        RETURN NEW;
    END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER update_profile_visibility
    BEFORE INSERT OR UPDATE ON participants
    FOR EACH ROW EXECUTE PROCEDURE update_profile_visibility();

-- migration #144
CREATE TYPE account_mark AS ENUM (
    'trusted', 'okay', 'unsettling',
    'controversial', 'irrelevant', 'misleading',
    'spam', 'fraud'
);
ALTER TABLE participants
    ADD COLUMN marked_as account_mark,
    ADD COLUMN is_unsettling int NOT NULL DEFAULT 0;
CREATE OR REPLACE FUNCTION update_profile_visibility() RETURNS trigger AS $$
    BEGIN
        IF (NEW.marked_as IS NULL) THEN
            RETURN NEW;
        END IF;
        IF (NEW.marked_as = 'trusted') THEN
            NEW.is_suspended = false;
        ELSIF (NEW.marked_as IN ('fraud', 'spam')) THEN
            NEW.is_suspended = true;
        ELSE
            NEW.is_suspended = null;
        END IF;
        IF (NEW.marked_as = 'unsettling') THEN
            NEW.is_unsettling = NEW.is_unsettling | 2;
        ELSE
            NEW.is_unsettling = NEW.is_unsettling & 2147483645;
        END IF;
        IF (NEW.marked_as IN ('okay', 'trusted')) THEN
            NEW.profile_noindex = NEW.profile_noindex & 2147483645;
            NEW.hide_from_lists = NEW.hide_from_lists & 2147483645;
            NEW.hide_from_search = NEW.hide_from_search & 2147483645;
        ELSIF (NEW.marked_as = 'unsettling') THEN
            NEW.profile_noindex = NEW.profile_noindex | 2;
            NEW.hide_from_lists = NEW.hide_from_lists & 2147483645;
            NEW.hide_from_search = NEW.hide_from_search & 2147483645;
        ELSE
            NEW.profile_noindex = NEW.profile_noindex | 2;
            NEW.hide_from_lists = NEW.hide_from_lists | 2;
            NEW.hide_from_search = NEW.hide_from_search | 2;
        END IF;
        RETURN NEW;
    END;
$$ LANGUAGE plpgsql;
UPDATE participants
   SET marked_as = 'spam'
 WHERE is_spam
   AND marked_as IS NULL;
UPDATE participants
   SET marked_as = 'controversial'
 WHERE is_controversial
   AND marked_as IS NULL;
UPDATE participants
   SET marked_as = 'trusted'
 WHERE is_suspended IS FALSE
   AND marked_as IS NULL;
ALTER TABLE participants
    DROP COLUMN is_controversial,
    DROP COLUMN is_spam;
WITH _events AS (
    SELECT DISTINCT ON (e.participant)
           e.participant
         , ( CASE WHEN e.payload->>'profile_noindex' = 'false'
                  THEN p.profile_noindex & 2147483645
                  ELSE p.profile_noindex | 2
             END
           ) AS profile_noindex
         , ( CASE WHEN e.payload->>'hide_from_lists' = 'true'
                  THEN p.hide_from_lists | 2
                  ELSE p.hide_from_lists & 2147483645
             END
           ) AS hide_from_lists
         , ( CASE WHEN e.payload->>'hide_from_search' = 'true'
                  THEN p.hide_from_search | 2
                  ELSE p.hide_from_search & 2147483645
             END
           ) AS hide_from_search
      FROM events e
      JOIN participants p ON p.id = e.participant
     WHERE e.type = 'visibility_override'
  ORDER BY e.participant, e.ts DESC
)
UPDATE participants p
   SET profile_noindex = e.profile_noindex
     , hide_from_lists = e.hide_from_lists
     , hide_from_search = e.hide_from_search
  FROM _events e
 WHERE e.participant = p.id
   AND p.marked_as IS NULL
   AND ( p.profile_noindex <> e.profile_noindex OR
         p.hide_from_lists <> e.hide_from_lists OR
         p.hide_from_search <> e.hide_from_search
       )
   AND NOT EXISTS (
           SELECT 1
             FROM events e2
            WHERE e2.participant = p.id
              AND e2.type = 'flags_changed'
       );
UPDATE participants
   SET marked_as = 'okay'
 WHERE profile_noindex < 2
   AND hide_from_lists < 2
   AND hide_from_search < 2
   AND marked_as IS NULL
   AND is_suspended IS NULL;

-- migration #145
DELETE FROM app_conf WHERE key = 'trusted_proxies';
ALTER TABLE rate_limiting SET LOGGED;

-- migration #146
DELETE FROM notifications WHERE event IN (
    'dispute',
    'low_balance',
    'payin_bankwire_created',
    'payin_bankwire_expired',
    'payin_bankwire_failed',
    'payin_bankwire_succeeded',
    'payin_directdebit_failed',
    'payin_directdebit_succeeded'
);

-- migration #147
CREATE OR REPLACE FUNCTION max(currency_amount, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        IF ($2.amount > $1.amount) THEN
            RETURN $2;
        ELSE
            RETURN $1;
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OR REPLACE AGGREGATE max(currency_amount) (
    sfunc = max,
    stype = currency_amount
);
CREATE OR REPLACE FUNCTION min(currency_amount, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        IF ($2.amount < $1.amount) THEN
            RETURN $2;
        ELSE
            RETURN $1;
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
CREATE OR REPLACE AGGREGATE min(currency_amount) (
    sfunc = min,
    stype = currency_amount
);

-- migration #148
ALTER TABLE elsewhere DROP COLUMN extra_info;
ALTER TABLE repositories DROP COLUMN extra_info;

-- migration #149
UPDATE redirections SET from_prefix = substring(from_prefix for length(from_prefix) - 1) WHERE right(from_prefix, 1) = '%';

-- migration #150
ALTER TABLE tips ADD COLUMN visibility int CHECK (visibility >= -3 AND visibility <> 0 AND visibility <= 3);
ALTER TABLE payin_transfers ADD COLUMN visibility int DEFAULT 1 CHECK (visibility >= 1 AND visibility <= 3);
UPDATE tips SET visibility = -1 WHERE hidden AND visibility IS NULL;
CREATE OR REPLACE VIEW current_tips AS
    SELECT DISTINCT ON (tipper, tippee) *
      FROM tips
  ORDER BY tipper, tippee, mtime DESC;
CREATE TABLE recipient_settings
( participant           bigint   PRIMARY KEY REFERENCES participants
, patron_visibilities   int      NOT NULL CHECK (patron_visibilities > 0)
);
UPDATE tips SET visibility = -1 WHERE hidden AND visibility = 1;
UPDATE tips SET visibility = 1 WHERE visibility IS NULL;
DROP FUNCTION compute_arrears(current_tips);
DROP CAST (current_tips AS tips);
DROP VIEW current_tips;
ALTER TABLE tips
    DROP COLUMN hidden,
    ALTER COLUMN visibility DROP DEFAULT,
    ALTER COLUMN visibility SET NOT NULL;
CREATE OR REPLACE VIEW current_tips AS
    SELECT DISTINCT ON (tipper, tippee) *
      FROM tips
  ORDER BY tipper, tippee, mtime DESC;
CREATE CAST (current_tips AS tips) WITH INOUT;
CREATE FUNCTION compute_arrears(tip current_tips) RETURNS currency_amount AS $$
    SELECT compute_arrears(tip::tips);
$$ LANGUAGE sql;
ALTER TABLE payin_transfers
    ALTER COLUMN visibility DROP DEFAULT,
    ALTER COLUMN visibility SET NOT NULL;

-- migration #151
ALTER TYPE route_status ADD VALUE IF NOT EXISTS 'expired';
UPDATE exchange_routes
   SET status = 'expired'
 WHERE id IN (
           SELECT DISTINCT ON (pi.route) pi.route
             FROM payins pi
            WHERE pi.error = 'Your card has expired. (code expired_card)'
         ORDER BY pi.route, pi.ctime DESC
       );

-- migration #152
CREATE INDEX transfers_team_idx ON transfers (team) WHERE team IS NOT NULL;

-- migration #153
UPDATE exchange_routes AS r
   SET is_default = null
 WHERE is_default
   AND NOT EXISTS (
           SELECT 1
             FROM events e
            WHERE e.participant = r.participant
              AND e.type = 'set_default_route'
              AND e.payload = jsonb_build_object(
                      'id', r.id,
                      'network', r.network
                  )
       );

-- migration #154
DELETE FROM notifications WHERE event IN (
    'income',
    'once/mangopay-exodus',
    'withdrawal_created',
    'withdrawal_failed'
);
DELETE FROM app_conf WHERE key LIKE 'mangopay_%';
DROP TABLE cash_bundles;
DROP TRIGGER upsert_mangopay_user_id ON participants;
DROP FUNCTION upsert_mangopay_user_id();
DROP TABLE mangopay_users;
CREATE OR REPLACE FUNCTION initialize_amounts() RETURNS trigger AS $$
        BEGIN
            NEW.giving = coalesce_currency_amount(NEW.giving, NEW.main_currency);
            NEW.receiving = coalesce_currency_amount(NEW.receiving, NEW.main_currency);
            NEW.taking = coalesce_currency_amount(NEW.taking, NEW.main_currency);
            RETURN NEW;
        END;
    $$ LANGUAGE plpgsql;
ALTER TABLE participants DROP CONSTRAINT mangopay_chk;
ALTER TABLE participants DROP COLUMN balance;
ALTER TABLE participants DROP COLUMN mangopay_user_id;

-- migration #155
UPDATE participants SET email_lang = 'zh' WHERE email_lang = 'zh_Hant';
UPDATE participants
   SET email_lang = email_lang || '-' || (
           SELECT lower(e.payload->'headers'->>'Cf-Ipcountry')
             FROM events e
            WHERE e.participant = participants.id
              AND e.type = 'sign_up_request'
       )
 WHERE email_lang IS NOT NULL
   AND (email_lang || '-' || (
           SELECT lower(e.payload->'headers'->>'Cf-Ipcountry')
             FROM events e
            WHERE e.participant = participants.id
              AND e.type = 'sign_up_request'
       )) IN (
           'ar-ae', 'ar-bh', 'ar-dj', 'ar-dz', 'ar-eg', 'ar-eh', 'ar-er', 'ar-il', 'ar-iq',
           'ar-jo', 'ar-km', 'ar-kw', 'ar-lb', 'ar-ly', 'ar-ma', 'ar-mr', 'ar-om', 'ar-ps',
           'ar-qa', 'ar-sa', 'ar-sd', 'ar-so', 'ar-ss', 'ar-sy', 'ar-td', 'ar-tn', 'ar-ye',
           'ca-ad', 'ca-es', 'ca-fr', 'ca-it', 'cs-cz', 'da-dk', 'da-gl', 'de-at', 'de-be',
           'de-ch', 'de-de', 'de-it', 'de-li', 'de-lu', 'el-cy', 'el-gr', 'en-ae', 'en-ag',
           'en-ai', 'en-as', 'en-at', 'en-au', 'en-bb', 'en-be', 'en-bi', 'en-bm', 'en-bs',
           'en-bw', 'en-bz', 'en-ca', 'en-cc', 'en-ch', 'en-ck', 'en-cm', 'en-cx', 'en-cy',
           'en-de', 'en-dg', 'en-dk', 'en-dm', 'en-er', 'en-fi', 'en-fj', 'en-fk', 'en-fm',
           'en-gb', 'en-gd', 'en-gg', 'en-gh', 'en-gi', 'en-gm', 'en-gu', 'en-gy', 'en-hk',
           'en-ie', 'en-il', 'en-im', 'en-in', 'en-io', 'en-je', 'en-jm', 'en-ke', 'en-ki',
           'en-kn', 'en-ky', 'en-lc', 'en-lr', 'en-ls', 'en-mg', 'en-mh', 'en-mo', 'en-mp',
           'en-ms', 'en-mt', 'en-mu', 'en-mw', 'en-my', 'en-na', 'en-nf', 'en-ng', 'en-nl',
           'en-nr', 'en-nu', 'en-nz', 'en-pg', 'en-ph', 'en-pk', 'en-pn', 'en-pr', 'en-pw',
           'en-rw', 'en-sb', 'en-sc', 'en-sd', 'en-se', 'en-sg', 'en-sh', 'en-si', 'en-sl',
           'en-ss', 'en-sx', 'en-sz', 'en-tc', 'en-tk', 'en-to', 'en-tt', 'en-tv', 'en-tz',
           'en-ug', 'en-um', 'en-us', 'en-vc', 'en-vg', 'en-vi', 'en-vu', 'en-ws', 'en-za',
           'en-zm', 'en-zw', 'es-ar', 'es-bo', 'es-br', 'es-bz', 'es-cl', 'es-co', 'es-cr',
           'es-cu', 'es-do', 'es-ea', 'es-ec', 'es-es', 'es-gq', 'es-gt', 'es-hn', 'es-ic',
           'es-mx', 'es-ni', 'es-pa', 'es-pe', 'es-ph', 'es-pr', 'es-py', 'es-sv', 'es-us',
           'es-uy', 'es-ve', 'et-ee', 'fi-fi', 'fr-be', 'fr-bf', 'fr-bi', 'fr-bj', 'fr-bl',
           'fr-ca', 'fr-cd', 'fr-cf', 'fr-cg', 'fr-ch', 'fr-ci', 'fr-cm', 'fr-dj', 'fr-dz',
           'fr-fr', 'fr-ga', 'fr-gf', 'fr-gn', 'fr-gp', 'fr-gq', 'fr-ht', 'fr-km', 'fr-lu',
           'fr-ma', 'fr-mc', 'fr-mf', 'fr-mg', 'fr-ml', 'fr-mq', 'fr-mr', 'fr-mu', 'fr-nc',
           'fr-ne', 'fr-pf', 'fr-pm', 'fr-re', 'fr-rw', 'fr-sc', 'fr-sn', 'fr-sy', 'fr-td',
           'fr-tg', 'fr-tn', 'fr-vu', 'fr-wf', 'fr-yt', 'fy-nl', 'ga-gb', 'ga-ie', 'hu-hu',
           'id-id', 'it-ch', 'it-it', 'it-sm', 'it-va', 'ja-jp', 'ko-kp', 'ko-kr', 'lt-lt',
           'lv-lv', 'ms-bn', 'ms-id', 'ms-my', 'ms-sg', 'nb-no', 'nb-sj', 'nl-aw', 'nl-be',
           'nl-bq', 'nl-cw', 'nl-nl', 'nl-sr', 'nl-sx', 'pl-pl', 'pt-ao', 'pt-br', 'pt-ch',
           'pt-cv', 'pt-gq', 'pt-gw', 'pt-lu', 'pt-mo', 'pt-mz', 'pt-pt', 'pt-st', 'pt-tl',
           'ro-md', 'ro-ro', 'ru-by', 'ru-kg', 'ru-kz', 'ru-md', 'ru-ru', 'ru-ua', 'sk-sk',
           'sl-si', 'sv-ax', 'sv-fi', 'sv-se', 'tr-cy', 'tr-tr', 'uk-ua', 'vi-vn', 'zh-cn',
           'zh-hk', 'zh-mo', 'zh-sg', 'zh-tw'
       );
UPDATE participants SET email_lang = 'zh-hans-cn' WHERE email_lang = 'zh-cn';
UPDATE participants SET email_lang = 'zh-hant-hk' WHERE email_lang = 'zh-hk';
UPDATE participants SET email_lang = 'zh-hant-mo' WHERE email_lang = 'zh-mo';
UPDATE participants SET email_lang = 'zh-hans-sg' WHERE email_lang = 'zh-sg';
UPDATE participants SET email_lang = 'zh-hant-tw' WHERE email_lang = 'zh-tw';
UPDATE participants SET email_lang = 'zh-hant' WHERE email_lang = 'zh';

-- migration #156
CREATE TABLE feedback
( participant   bigint      PRIMARY KEY
, feedback      text        NOT NULL
, ctime         timestamptz NOT NULL DEFAULT current_timestamp
);

-- migration #157
CREATE FUNCTION check_payin_transfer_update() RETURNS trigger AS $$
    BEGIN
        IF (OLD.status = 'succeeded' AND NEW.status = 'succeeded') THEN
            IF (NEW.amount <> OLD.amount) THEN
                RAISE 'modifying the amount of an already successful transfer is not allowed';
            END IF;
        END IF;
        RETURN NEW;
    END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER check_payin_transfer_update BEFORE UPDATE ON payin_transfers
    FOR EACH ROW EXECUTE PROCEDURE check_payin_transfer_update();
UPDATE payins SET remote_id = null WHERE remote_id = '';
UPDATE payin_transfers SET remote_id = null WHERE remote_id = '';

-- migration #158
ALTER TABLE participants ALTER COLUMN email_notif_bits SET DEFAULT 2147483646;
DELETE FROM notifications WHERE event = 'income~v2' AND NOT email;
UPDATE notifications SET web = false WHERE event = 'income~v2';

-- migration #159
UPDATE payins SET error = 'abandoned py payer' WHERE error = 'expired';
UPDATE payin_events SET error = 'abandoned py payer' WHERE error = 'expired';
UPDATE payin_transfers SET error = 'abandoned py payer' WHERE error = 'expired';
UPDATE payin_transfer_events SET error = 'abandoned py payer' WHERE error = 'expired';
WITH closed as (
    UPDATE participants
       SET status = 'closed'
     WHERE kind = 'group'
       AND status = 'active'
       AND NOT EXISTS (
               SELECT 1
                 FROM current_takes take
                WHERE take.team = participants.id
           )
 RETURNING id
)
INSERT INTO events (participant, type, payload)
     SELECT id, 'set_status', '"closed"'
       FROM closed;

-- migration #160
CREATE OR REPLACE FUNCTION compute_payment_providers(bigint) RETURNS bigint AS $$
    SELECT CASE WHEN p.email IS NULL AND p.kind <> 'group' AND p.join_time >= '2022-12-06' THEN 0
           ELSE coalesce((
               SELECT sum(DISTINCT array_position(
                                       enum_range(NULL::payment_providers),
                                       a.provider::payment_providers
                                   ))
                 FROM payment_accounts a
                WHERE ( a.participant = p.id OR
                        a.participant IN (
                            SELECT t.member
                              FROM current_takes t
                             WHERE t.team = p.id
                               AND t.amount <> 0
                        )
                      )
                  AND a.is_current IS TRUE
                  AND a.verified IS TRUE
                  AND coalesce(a.charges_enabled, true)
           ), 0) END
      FROM participants p
     WHERE p.id = $1;
$$ LANGUAGE SQL STRICT;

-- migration #161
ALTER TYPE payin_status ADD VALUE IF NOT EXISTS 'awaiting_review';
ALTER TYPE payin_transfer_status ADD VALUE IF NOT EXISTS 'awaiting_review';
CREATE INDEX payins_awating_review ON payins (status) WHERE status = 'awaiting_review';

-- migration #162
INSERT INTO currency_exchange_rates
     VALUES ('HRK', 'EUR', 1 / 7.53450)
          , ('EUR', 'HRK', 7.53450)
ON CONFLICT (source_currency, target_currency) DO UPDATE
        SET rate = excluded.rate;
UPDATE participants
   SET main_currency = 'EUR'
     , goal = convert(goal, 'EUR')
     , giving = convert(giving, 'EUR')
     , receiving = convert(receiving, 'EUR')
     , taking = convert(taking, 'EUR')
 WHERE main_currency = 'HRK';
UPDATE participants p
   SET accepted_currencies = (CASE
           WHEN accepted_currencies LIKE '%EUR%'
           THEN replace(regexp_replace(regexp_replace(accepted_currencies, '^HRK,', ''), ',HRK$', ''), ',HRK,', ',')
           ELSE replace(accepted_currencies, 'HRK', 'EUR')
       END)
 WHERE accepted_currencies LIKE '%HRK%';
INSERT INTO tips
          ( ctime, tipper, tippee
          , amount, period, periodic_amount
          , paid_in_advance, is_funded, renewal_mode, visibility )
     SELECT ctime, tipper, tippee
          , convert(amount, 'EUR'), period, convert(periodic_amount, 'EUR')
          , convert(paid_in_advance, 'EUR'), is_funded, renewal_mode, visibility
       FROM current_tips
      WHERE (amount).currency = 'HRK';
UPDATE scheduled_payins
   SET amount = convert(amount, 'EUR')
 WHERE (amount).currency = 'HRK';
INSERT INTO takes
            (ctime, member, team, amount, actual_amount, recorder, paid_in_advance)
     SELECT ctime, member, team, convert(amount, 'EUR'), actual_amount, recorder, convert(paid_in_advance, 'EUR')
       FROM current_takes
      WHERE (amount).currency = 'HRK';

-- migration #163
CREATE TABLE cron_jobs
( name                text          PRIMARY KEY
, last_start_time     timestamptz
, last_success_time   timestamptz
, last_error_time     timestamptz
, last_error          text
);

-- migration #164
CREATE OR REPLACE FUNCTION compute_payment_providers(bigint) RETURNS bigint AS $$
    SELECT coalesce((
        SELECT sum(DISTINCT array_position(
                                enum_range(NULL::payment_providers),
                                a.provider::payment_providers
                            ))
          FROM payment_accounts a
         WHERE ( a.participant = $1 OR
                 a.participant IN (
                     SELECT t.member
                       FROM current_takes t
                      WHERE t.team = $1
                        AND t.amount <> 0
                 )
               )
           AND a.is_current IS TRUE
           AND a.verified IS TRUE
           AND coalesce(a.charges_enabled, true)
    ), 0);
$$ LANGUAGE SQL STRICT;
UPDATE participants
   SET payment_providers = compute_payment_providers(id)
 WHERE status <> 'stub'
   AND payment_providers = 0
   AND email IS NOT NULL
   AND join_time >= '2022-12-06'
   AND compute_payment_providers(id) <> 0;

-- migration #165
UPDATE payins SET error = '' WHERE error = 'None (code None)';
UPDATE payin_events SET error = '' WHERE error = 'None (code None)';
ALTER TYPE payin_transfer_status ADD VALUE IF NOT EXISTS 'suspended';

-- migration #166
CREATE OR REPLACE FUNCTION update_profile_visibility() RETURNS trigger AS $$
    BEGIN
        IF (OLD.marked_as IS NULL AND NEW.marked_as IS NULL) THEN
            RETURN NEW;
        END IF;
        IF (NEW.marked_as = 'trusted') THEN
            NEW.is_suspended = false;
        ELSIF (NEW.marked_as IN ('fraud', 'spam')) THEN
            NEW.is_suspended = true;
        ELSE
            NEW.is_suspended = null;
        END IF;
        IF (NEW.marked_as = 'unsettling') THEN
            NEW.is_unsettling = NEW.is_unsettling | 2;
        ELSE
            NEW.is_unsettling = NEW.is_unsettling & 2147483645;
        END IF;
        IF (NEW.marked_as IN ('okay', 'trusted')) THEN
            NEW.profile_noindex = NEW.profile_noindex & 2147483645;
            NEW.hide_from_lists = NEW.hide_from_lists & 2147483645;
            NEW.hide_from_search = NEW.hide_from_search & 2147483645;
        ELSIF (NEW.marked_as IS NULL) THEN
            NEW.profile_noindex = NEW.profile_noindex | 2;
            NEW.hide_from_lists = NEW.hide_from_lists & 2147483645;
            NEW.hide_from_search = NEW.hide_from_search & 2147483645;
        ELSE
            NEW.profile_noindex = NEW.profile_noindex | 2;
            NEW.hide_from_lists = NEW.hide_from_lists | 2;
            NEW.hide_from_search = NEW.hide_from_search | 2;
        END IF;
        RETURN NEW;
    END;
$$ LANGUAGE plpgsql;
UPDATE participants
   SET marked_as = marked_as
 WHERE marked_as = 'unsettling';
UPDATE participants AS p
   SET is_suspended = null
     , is_unsettling = is_unsettling & 2147483645
     , profile_noindex = profile_noindex | 2
     , hide_from_lists = hide_from_lists & 2147483645
     , hide_from_search = hide_from_search & 2147483645
 WHERE marked_as IS NULL AND EXISTS (
           SELECT 1
             FROM events e
            WHERE e.participant = p.id
              AND e.type = 'flags_changed'
            LIMIT 1
       );
UPDATE payin_transfers SET error = '' WHERE error = 'None (code None)';
UPDATE payin_transfer_events SET error = '' WHERE error = 'None (code None)';
INSERT INTO app_conf VALUES
    ('twitter_id', '"ikgMaoYPSKqCpQJkVtiRHvmqv"'::jsonb),
    ('twitter_secret', '"pwInmJX3vSRuul2mqYs8iJsdkmcXSkBbYh7KB9wqK2pmkJQNm9"'::jsonb)
    ON CONFLICT (key) DO UPDATE SET value = excluded.value;

-- migration #167
CREATE OR REPLACE FUNCTION update_payment_accounts() RETURNS trigger AS $$
    BEGIN
        UPDATE payment_accounts
           SET verified = coalesce(NEW.verified, false)
         WHERE participant = NEW.participant
           AND lower(id) = lower(NEW.address);
        RETURN NULL;
    END;
$$ LANGUAGE plpgsql;
UPDATE payment_accounts AS a
   SET verified = true
 WHERE lower(id) <> id
   AND NOT verified
   AND EXISTS (
           SELECT 1
             FROM emails e
            WHERE e.participant = a.participant
              AND lower(e.address) = lower(a.id)
              AND e.verified
       );

-- migration #168
ALTER TABLE exchange_routes ADD COLUMN is_default_for currency;

-- migration #169
ALTER TABLE elsewhere ADD COLUMN last_fetch_attempt timestamptz;
ALTER TABLE repositories ADD COLUMN last_fetch_attempt timestamptz;
DELETE FROM rate_limiting WHERE key LIKE 'refetch_%';

-- migration #170
CREATE TYPE localized_string AS (string text, lang text);

-- migration #171
UPDATE app_conf SET value = '"https://api.openstreetmap.org/api/0.6"'::jsonb WHERE key = 'openstreetmap_api_url';
UPDATE app_conf SET value = '"https://www.openstreetmap.org"'::jsonb WHERE key = 'openstreetmap_auth_url';

-- migration #172
UPDATE participants
   SET avatar_url = 'https://pbs.twimg.com/' || regexp_replace(substr(avatar_url, 24), '%2F', '/', 'g')
 WHERE avatar_url LIKE 'https://nitter.net/pic/%';

-- migration #173
DELETE FROM elsewhere WHERE platform in ('facebook', 'google');
DELETE FROM app_conf WHERE key LIKE 'facebook_%';

-- migration #174
CREATE TEMPORARY TABLE _tippees AS (
    SELECT e.participant AS id
         , (CASE WHEN e.payload->>'patron_visibilities' = '2' THEN 2 ELSE 3 END) AS only_accepted_visibility
         , e.ts AS start_time
         , coalesce((
               SELECT e2.ts
                 FROM events e2
                WHERE e2.participant = e.participant
                  AND e2.type = 'recipient_settings'
                  AND e2.ts > e.ts
             ORDER BY e2.ts
                LIMIT 1
           ), current_timestamp) AS end_time
      FROM events e
     WHERE e.type = 'recipient_settings'
       AND e.payload->>'patron_visibilities' IN ('2', '4')
);
UPDATE tips AS tip
   SET visibility = tippee.only_accepted_visibility
  FROM _tippees AS tippee
 WHERE tip.tippee = tippee.id
   AND tip.mtime > tippee.start_time
   AND tip.mtime < tippee.end_time
   AND tip.visibility <> tippee.only_accepted_visibility;
UPDATE payin_transfers AS pt
   SET visibility = tippee.only_accepted_visibility
  FROM _tippees AS tippee
 WHERE pt.recipient = tippee.id
   AND pt.ctime > tippee.start_time
   AND pt.ctime < tippee.end_time
   AND pt.visibility <> tippee.only_accepted_visibility;
DROP TABLE _tippees;

-- migration #175
INSERT INTO app_conf VALUES ('openstreetmap_access_token_url', '"https://master.apis.dev.openstreetmap.org/oauth2/token"') ON CONFLICT (key) DO NOTHING;
UPDATE app_conf SET value = '"https://master.apis.dev.openstreetmap.org/api/0.6"' WHERE key = 'openstreetmap_api_url';
UPDATE app_conf SET value = '"https://master.apis.dev.openstreetmap.org/oauth2/authorize"' WHERE key = 'openstreetmap_auth_url';
UPDATE app_conf SET value = '"xAVaXxy0BwUef4SIo55v7E1ofuC53EN8H-X5232d8Vo"' WHERE key = 'openstreetmap_id';
UPDATE app_conf SET value = '"JtqazsotvWZQ1G6ynYhDlHXouQji-qDwwU2WQW7j-kE"' WHERE key = 'openstreetmap_secret';

-- migration #176
ALTER TABLE recipient_settings
    ALTER COLUMN patron_visibilities DROP NOT NULL,
    ADD COLUMN patron_countries text CHECK (patron_countries <> '');

-- migration #177
CREATE INDEX public_name_trgm_idx ON participants
    USING GIN (lower(public_name) gin_trgm_ops)
    WHERE status = 'active'
      AND public_name IS NOT null;

-- migration #178
UPDATE exchange_routes SET is_default_for = 'EUR', is_default = null WHERE network = 'stripe-sdd' AND is_default;

-- migration #179
ALTER TABLE user_secrets ADD COLUMN latest_use date;

-- migration #180
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'AED';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'AFN';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'ALL';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'AMD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'ANG';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'AOA';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'ARS';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'AWG';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'AZN';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BAM';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BBD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BDT';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BIF';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BMD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BND';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BOB';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BSD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BWP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BYN';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BZD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'CDF';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'CLP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'COP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'CRC';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'CVE';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'DJF';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'DOP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'DZD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'EGP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'ETB';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'FJD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'FKP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'GEL';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'GIP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'GMD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'GNF';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'GTQ';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'GYD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'HNL';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'HTG';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'JMD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'KES';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'KGS';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'KHR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'KMF';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'KYD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'KZT';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'LAK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'LBP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'LKR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'LRD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'LSL';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MAD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MDL';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MGA';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MKD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MMK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MNT';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MOP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MUR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MVR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MWK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MZN';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'NAD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'NGN';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'NIO';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'NPR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'PAB';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'PEN';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'PGK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'PKR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'PYG';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'QAR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'RSD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'RWF';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'SAR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'SBD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'SCR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'SHP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'SLE';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'SOS';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'SRD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'SZL';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'TJS';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'TOP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'TTD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'TWD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'TZS';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'UAH';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'UGX';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'UYU';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'UZS';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'VND';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'VUV';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'WST';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'XAF';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'XCD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'XOF';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'XPF';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'YER';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'ZMW';
INSERT INTO app_conf VALUES ('fixer_access_key', 'null'::jsonb) ON CONFLICT (key) DO NOTHING;

-- migration #181
ALTER TABLE exchange_routes
    ADD COLUMN brand text,
    ADD COLUMN last4 text,
    ADD COLUMN fingerprint text,
    ADD COLUMN owner_name text,
    ADD COLUMN expiration_date date,
    ADD COLUMN mandate_reference text;

-- migration #182
UPDATE participants SET public_name = null WHERE public_name = '';

-- migration #183
DROP INDEX events_admin_idx;
CREATE INDEX events_admin_idx ON events (ts DESC) WHERE type IN ('admin_request', 'flags_changed');

-- migration #184
ALTER TABLE payins
    ADD COLUMN allowed_by bigint REFERENCES participants,
    ADD COLUMN allowed_since timestamptz,
    ADD CONSTRAINT allowed_chk CHECK ((allowed_since IS NULL) = (allowed_by IS NULL));
DROP INDEX events_admin_idx;
CREATE INDEX events_admin_idx ON events (ts DESC) WHERE type IN ('admin_request', 'flags_changed', 'payin_review');

-- migration #185
UPDATE exchange_routes
   SET currency = 'EUR'
 WHERE network = 'stripe-sdd'
   AND currency IS NULL;

-- migration #186
CREATE TYPE loss_taker AS ENUM ('provider', 'platform');
ALTER TABLE payment_accounts
    ADD COLUMN independent boolean DEFAULT true,
    ADD COLUMN loss_taker loss_taker DEFAULT 'provider',
    ADD COLUMN details_submitted boolean,
    ADD COLUMN allow_payout boolean,
    DROP CONSTRAINT payment_accounts_participant_provider_country_is_current_key;
CREATE INDEX payment_accounts_participant_provider_country_is_current_idx
    ON payment_accounts (participant, provider, country, is_current);
ALTER TABLE payment_accounts
    ALTER COLUMN independent DROP DEFAULT,
    ALTER COLUMN loss_taker DROP DEFAULT;

-- migration #187
CREATE OR REPLACE FUNCTION hit_rate_limit(key text, cap int, period float) RETURNS int AS $$
    INSERT INTO rate_limiting AS r
                (key, counter, ts)
         VALUES (key, 1, current_timestamp)
    ON CONFLICT (key) DO UPDATE
            SET counter = r.counter + 1 - least(compute_leak(cap, period, r.ts), r.counter)
              , ts = current_timestamp
          WHERE (r.counter - compute_leak(cap, period, r.ts)) < cap
             OR r.ts < (current_timestamp - make_interval(secs => period / cap * 0.8))
      RETURNING cap - counter;
$$ LANGUAGE sql;

-- migration #188
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'XCG';
UPDATE participants
   SET main_currency = 'XCG'
     , goal = ((goal).amount, 'XCG')::currency_amount
     , giving = ((giving).amount, 'XCG')::currency_amount
     , receiving = ((receiving).amount, 'XCG')::currency_amount
     , taking = ((taking).amount, 'XCG')::currency_amount
 WHERE main_currency = 'ANG';
UPDATE participants p
   SET accepted_currencies = replace(accepted_currencies, 'ANG', 'XCG')
 WHERE accepted_currencies LIKE '%ANG%';
INSERT INTO tips
          ( ctime, tipper, tippee
          , amount, period
          , periodic_amount
          , paid_in_advance
          , is_funded, renewal_mode, visibility )
     SELECT ctime, tipper, tippee
          , ((amount).amount, 'XCG')::currency_amount, period
          , ((periodic_amount).amount, 'XCG')::currency_amount
          , ((paid_in_advance).amount, 'XCG')::currency_amount
          , is_funded, renewal_mode, visibility
       FROM current_tips
      WHERE (amount).currency = 'ANG';
UPDATE scheduled_payins
   SET amount = ((amount).amount, 'XCG')::currency_amount
 WHERE (amount).currency = 'ANG';
INSERT INTO takes
            ( ctime, member, team, amount
            , actual_amount, recorder, paid_in_advance)
     SELECT ctime, member, team, ((amount).amount, 'XCG')::currency_amount
          , actual_amount, recorder, ((paid_in_advance).amount, 'XCG')::currency_amount
       FROM current_takes
      WHERE (amount).currency = 'ANG';

-- migration #189
ALTER TYPE account_mark ADD VALUE IF NOT EXISTS 'obsolete';
ALTER TYPE account_mark ADD VALUE IF NOT EXISTS 'out-of-scope';
ALTER TYPE account_mark ADD VALUE IF NOT EXISTS 'unverifiable';

-- migration #190
ALTER TABLE payin_events ADD COLUMN remote_timestamp timestamptz;
ALTER TABLE payin_transfer_events ADD COLUMN remote_timestamp timestamptz;

-- migration #191
CREATE INDEX payin_transfers_team_idx ON payin_transfers (team);
