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
