CREATE TABLE exchange_events
( id             bigserial         PRIMARY KEY
, timestamp      timestamptz       NOT NULL DEFAULT current_timestamp
, exchange       int               NOT NULL REFERENCES exchanges
, status         exchange_status   NOT NULL
, error          text
, wallet_delta   currency_amount
, UNIQUE (exchange, status)
);
