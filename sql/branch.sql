CREATE TABLE user_passwords
( participant   bigint        PRIMARY KEY REFERENCES participants
, password      text          NOT NULL
, mtime         timestamptz   NOT NULL DEFAULT current_timestamp
);

CREATE TABLE user_sessions
( participant   bigint        PRIMARY KEY REFERENCES participants
, token         text          NOT NULL
, expires_at    timestamptz   NOT NULL DEFAULT current_timestamp
);

CREATE FUNCTION _fill_new_tables() RETURNS void AS $$

    INSERT INTO user_passwords
                (participant, password, mtime)
         SELECT p.id, p.password, p.password_mtime
           FROM participants p
          WHERE p.password IS NOT NULL
       ORDER BY p.password_mtime ASC
    ON CONFLICT (participant) DO UPDATE
            SET password = excluded.password
              , mtime = excluded.mtime;

    INSERT INTO user_sessions
                (participant, token, expires_at)
         SELECT p.id, session_token, p.session_expires
           FROM participants p
          WHERE p.session_token IS NOT NULL
       ORDER BY p.session_expires ASC
    ON CONFLICT (participant) DO UPDATE
            SET token = excluded.token
              , expires_at = excluded.expires_at;

$$ LANGUAGE SQL;

SELECT _fill_new_tables();

SELECT 'after deployment';

SELECT _fill_new_tables();

DROP FUNCTION _fill_new_tables();

ALTER TABLE participants
    DROP COLUMN password,
    DROP COLUMN password_mtime,
    DROP COLUMN session_token,
    DROP COLUMN session_expires;
