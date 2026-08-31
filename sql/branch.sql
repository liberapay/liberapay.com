CREATE TABLE user_webauthn_credentials
( participant      bigint        NOT NULL REFERENCES participants
, id               int           NOT NULL
, name             text          NOT NULL
, credential_id    text          NOT NULL
, public_key       text          NOT NULL
, latest_counter   bigint
, ctime            timestamptz   NOT NULL DEFAULT current_timestamp
, mtime            timestamptz   NOT NULL DEFAULT current_timestamp
, UNIQUE (participant, id)
, UNIQUE (credential_id)
);
