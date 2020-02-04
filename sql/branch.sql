BEGIN;
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
END;

SELECT 'after deployment';

ALTER TABLE payins ALTER COLUMN off_session DROP DEFAULT;
