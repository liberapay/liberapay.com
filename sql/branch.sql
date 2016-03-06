CREATE TABLE e2e_transfers
( id           bigserial      PRIMARY KEY
, origin       bigint         NOT NULL REFERENCES exchanges
, withdrawal   bigint         NOT NULL REFERENCES exchanges
, amount       numeric(35,2)  NOT NULL CHECK (amount > 0)
);

ALTER TABLE exchanges ADD CONSTRAINT exchanges_amount_check CHECK (amount <> 0);
