BEGIN;

ALTER TABLE participants ADD COLUMN notify_on_opt_in boolean NOT NULL DEFAULT true;

CREATE TABLE email_queue
( id            serial   PRIMARY KEY
, participant   bigint   NOT NULL REFERENCES participants(id)
, spt_name      text     NOT NULL
, context       bytea    NOT NULL
);

END;
