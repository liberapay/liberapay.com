ALTER TABLE users
  ADD COLUMN created            timestamp       NOT NULL DEFAULT 'now'
, ADD COLUMN is_admin           boolean         NOT NULL DEFAULT FALSE
, ADD COLUMN sponsor_since      date            DEFAULT NULL
, ADD COLUMN sponsor_through    date            DEFAULT NULL
 ;
