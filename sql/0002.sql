ALTER TABLE users
  ADD COLUMN created            timestamp       NOT NULL DEFAULT 'now'
, ADD COLUMN subscribed_on      date            DEFAULT NULL
, ADD COLUMN subscribed_through date            DEFAULT NULL
 ;
