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
