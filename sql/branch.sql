BEGIN;

CREATE TABLE feedback
( participant   bigint      PRIMARY KEY
, feedback      text        NOT NULL
, ctime         timestamptz NOT NULL DEFAULT current_timestamp
);

END;