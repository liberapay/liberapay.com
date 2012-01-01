CREATE TABLE users (
    email                   varchar(64)     PRIMARY KEY,
    hash                    char(40)        NOT NULL,
    payment_method_token    text            DEFAULT NULL,
    session_token           char(36)        DEFAULT NULL,
    session_expires         timestamp       DEFAULT 'now'
);

-- Max amount is $999,999,999,999,999.99.
CREATE TABLE transactions (
    id      serial          PRIMARY KEY,
    email   varchar(64)     REFERENCES users (email),
    amount  numeric(15,2)   NOT NULL,
    ts      timestamp       NOT NULL DEFAULT 'now'
);

