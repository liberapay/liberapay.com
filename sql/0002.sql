ALTER TABLE users
  ADD COLUMN created            timestamp       NOT NULL DEFAULT 'now'
, ADD COLUMN is_admin           boolean         NOT NULL DEFAULT FALSE
 ;
UPDATE users SET is_admin=true WHERE email='chad@zetaweb.com';
