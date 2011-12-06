DROP TABLE IF EXISTS users;

CREATE TABLE users (
    email                   varchar(255)    NOT NULL UNIQUE,
    hash                    char(40)        NOT NULL,
    teacher                 boolean         DEFAULT FALSE,
    session_token           char(36)        DEFAULT NULL,
    session_expires         timestamp       DEFAULT 'now',
    payment_method_token    text            DEFAULT NULL
);

INSERT INTO users (email, hash) 
    VALUES ('chad@zetaweb.com', 'cabd1aba5b11a4eef45d4015c003510e6a7c682c');
INSERT INTO users (email, hash) 
    VALUES ('christian@dowski.com', '657faae1aef3c3e7e806f8354a3e3f5b6839a76f');

--DROP ROLE logstown;
--CREATE ROLE logstown;
--ALTER ROLE logstown WITH LOGIN;
--ALTER ROLE logstown WITH PASSWORD 'blah';
--GRANT INSERT,SELECT,UPDATE,DELETE ON TABLE domains TO logstown;
--GRANT INSERT,SELECT,UPDATE,DELETE ON TABLE datasets TO logstown;
--GRANT SELECT,UPDATE ON TABLE datasets_id_seq TO logstown;

