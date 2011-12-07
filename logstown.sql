DROP TABLE IF EXISTS users CASCADE;
CREATE TABLE users (
    email                   varchar(255)    NOT NULL UNIQUE,
    hash                    char(40)        NOT NULL,
    id                      varchar(255)    PRIMARY KEY,
    payment_method_token    text            DEFAULT NULL,
    session_token           char(36)        DEFAULT NULL,
    session_expires         timestamp       DEFAULT 'now'
);

INSERT INTO users (id, email, hash) 
    VALUES ( 'chad@zetaweb.com'
           , 'chad@zetaweb.com'
           , 'cabd1aba5b11a4eef45d4015c003510e6a7c682c'
            );
INSERT INTO users (id, email, hash) 
    VALUES ( 'christian@dowski.com'
           , 'christian@dowski.com'
           , '657faae1aef3c3e7e806f8354a3e3f5b6839a76f'
            );

DROP TABLE IF EXISTS ledger;
-- Max amount is $999,999,999,999,999.99.
CREATE TABLE ledger (
    id      serial          PRIMARY KEY,
    user_id varchar(255)    REFERENCES users (id),
    amount  numeric(15,2)   NOT NULL,
    ts      timestamp       NOT NULL DEFAULT 'now'
);
