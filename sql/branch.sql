CREATE TABLE user_secrets
( participant   bigint        NOT NULL REFERENCES participants
, id            int           NOT NULL
, secret        text          NOT NULL
, mtime         timestamptz   NOT NULL DEFAULT current_timestamp
, UNIQUE (participant, id)
);

CREATE FUNCTION _upsert_user_secrets() RETURNS void AS $$

    INSERT INTO user_secrets
         SELECT p.id, 0, p.password, p.password_mtime
           FROM participants p
          WHERE p.password IS NOT NULL
    ON CONFLICT (participant, id) DO UPDATE
            SET secret = excluded.secret
              , mtime = excluded.mtime;

    INSERT INTO user_secrets
         SELECT p.id, 1, p.session_token, p.session_expires - interval '6 hours'
           FROM participants p
          WHERE p.session_token IS NOT NULL
            AND p.session_expires >= (current_timestamp - interval '30 days')
    ON CONFLICT (participant, id) DO UPDATE
            SET secret = excluded.secret
              , mtime = excluded.mtime;

$$ LANGUAGE SQL;

SELECT _upsert_user_secrets();

SELECT 'after deployment';

SELECT _upsert_user_secrets();

DROP FUNCTION _upsert_user_secrets();

ALTER TABLE participants
    DROP COLUMN password,
    DROP COLUMN password_mtime,
    DROP COLUMN session_token,
    DROP COLUMN session_expires;
