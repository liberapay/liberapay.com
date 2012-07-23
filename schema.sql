--                             million trillion trillion
--                             |         trillion trillion
--                             |         |               trillion
--                             |         |               |   billion
--                             |         |               |   |   million
--                             |         |               |   |   |   thousand
--                             |         |               |   |   |   | 
-- numeric(35,2) maxes out at $999,999,999,999,999,999,999,999,999,999,999.00.


-- Create the initial structure.

CREATE EXTENSION hstore;

CREATE TABLE participants 
( id                    text                        PRIMARY KEY 
, statement             text                        DEFAULT ''
    
, stripe_customer_id    text                        DEFAULT NULL
, last_bill_result      text                        DEFAULT NULL

, session_token         text                        UNIQUE DEFAULT NULL
, session_expires       timestamp with time zone    DEFAULT CURRENT_TIMESTAMP

, ctime                 timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, claimed_time          timestamp with time zone    DEFAULT NULL
, is_admin              boolean                     NOT NULL DEFAULT FALSE
, shares_giving         boolean                     NOT NULL DEFAULT TRUE

-- If this isn't NULL then it means one participant was folded into another
-- and all requests for this participant should be redirected to the other.
, redirect              text            DEFAULT NULL REFERENCES participants

-- The participants balance is expected to be receipts - disbursements. It is 
-- stored here as an optimization and sanity check.
, balance               numeric(35,2)               DEFAULT 0.0
, pending               numeric(35,2)               DEFAULT NULL
 );

CREATE TABLE social_network_users
( id                    serial          PRIMARY KEY
, network               text            NOT NULL
, user_id               text            NOT NULL
, user_info             hstore
, is_locked             boolean         NOT NULL DEFAULT FALSE
, participant_id        text            DEFAULT NULL REFERENCES participants ON DELETE RESTRICT
, UNIQUE(network, user_id)
 );

-- tips -- all times a participant elects to tip another
CREATE TABLE tips
( id                    serial                      PRIMARY KEY
, ctime                 timestamp with time zone    NOT NULL
, mtime                 timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, tipper                text                        NOT NULL REFERENCES participants ON DELETE RESTRICT
, tippee                text                        NOT NULL REFERENCES participants ON DELETE RESTRICT
, amount                numeric(35,2)               NOT NULL
 );

-- transfers -- balance transfers from one user to another
CREATE TABLE transfers 
( id                    serial                      PRIMARY KEY
, timestamp             timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, tipper                text                        NOT NULL REFERENCES participants ON DELETE RESTRICT
, tippee                text                        NOT NULL REFERENCES participants ON DELETE RESTRICT
, amount                numeric(35,2)               NOT NULL
 );

-- paydays -- payday events, stats about them
CREATE TABLE paydays
( id                    serial                      PRIMARY KEY
, ts_start              timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, ts_end                timestamp with time zone    UNIQUE NOT NULL DEFAULT '1970-01-01T00:00:00+00'::timestamptz
, nparticipants         bigint                      DEFAULT 0
, ntippers              bigint                      DEFAULT 0
, ntips                 bigint                      DEFAULT 0
, ntransfers            bigint                      DEFAULT 0
, transfer_volume       numeric(35,2)               DEFAULT 0.00
, ncc_failing           bigint                      DEFAULT 0
, ncc_missing           bigint                      DEFAULT 0
, nexchanges            bigint                      DEFAULT 0
, exchange_volume       numeric(35,2)               DEFAULT 0.00 
, exchange_fees_volume  numeric(35,2)               DEFAULT 0.00 
 );

-- exchanges -- when a participant moves cash between Gittip and their bank
CREATE TABLE exchanges
( id                    serial                      PRIMARY KEY
, timestamp             timestamp with time zone    NOT NULL DEFAULT CURRENT_TIMESTAMP
, amount                numeric(35,2)               NOT NULL
, fee                   numeric(35,2)               NOT NULL
, participant_id        text                        NOT NULL REFERENCES participants ON DELETE RESTRICT
 );


-- https://github.com/whit537/www.gittip.com/issues/128
ALTER TABLE participants ADD COLUMN anonymous bool NOT NULL DEFAULT FALSE;
ALTER TABLE participants DROP COLUMN shares_giving; 


-- https://github.com/whit537/www.gittip.com/issues/110
ALTER TABLE participants ADD COLUMN goal numeric(35,2) DEFAULT NULL;


-- https://github.com/whit537/www.gittip.com/issues/78
ALTER TABLE participants ADD COLUMN balanced_account_uri text DEFAULT NULL;

-- https://github.com/whit537/www.gittip.com/issues/161
ALTER TABLE participants ADD CONSTRAINT min_balance CHECK(balance >= 0);
