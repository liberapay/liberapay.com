DROP TABLE IF EXISTS users;

CREATE TABLE users (
    email   varchar(255)    NOT NULL UNIQUE,
    hash    char(40)        NOT NULL,
    teacher boolean         DEFAULT FALSE,
    token   char(36)        DEFAULT NULL,
    expires timestamp       DEFAULT 'now'
);

INSERT INTO users (email, hash) VALUES ('chad@zetaweb.com', 'cabd1aba5b11a4eef45d4015c003510e6a7c682c');

--DROP ROLE logstown;
--CREATE ROLE logstown;
--ALTER ROLE logstown WITH LOGIN;
--ALTER ROLE logstown WITH PASSWORD 'blah';
--GRANT INSERT,SELECT,UPDATE,DELETE ON TABLE domains TO logstown;
--GRANT INSERT,SELECT,UPDATE,DELETE ON TABLE datasets TO logstown;
--GRANT SELECT,UPDATE ON TABLE datasets_id_seq TO logstown;

