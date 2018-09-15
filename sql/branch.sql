CREATE TYPE blacklist_reason AS ENUM ('bounce', 'complaint');

CREATE TABLE email_blacklist
( address   text               NOT NULL
, ts        timestamptz        NOT NULL DEFAULT current_timestamp
, reason    blacklist_reason   NOT NULL
, details   text
, UNIQUE (lower(address))
);
