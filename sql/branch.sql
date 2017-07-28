ALTER TABLE cash_bundles ADD COLUMN disputed boolean;

ALTER TYPE transfer_context ADD VALUE IF NOT EXISTS 'chargeback';

CREATE TABLE disputes
( id              bigint          PRIMARY KEY
, creation_date   timestamptz     NOT NULL
, type            text            NOT NULL
, amount          numeric(35,2)   NOT NULL
, status          text            NOT NULL
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
