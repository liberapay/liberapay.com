BEGIN;
    CREATE TABLE balances_at
    ( participant  bigint         NOT NULL REFERENCES participants(id)
    , at           timestamptz    NOT NULL
    , balance      numeric(35,2)  NOT NULL
    , UNIQUE (participant, at)
    );
END;
