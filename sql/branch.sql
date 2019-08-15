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
