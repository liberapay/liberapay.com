BEGIN;

CREATE TABLE feedback
( participant   bigint      PRIMARY KEY
, feedback      text        NOT NULL
);

END;