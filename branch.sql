-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/1582

ALTER TABLE participants ADD COLUMN paypal_email text DEFAULT NULL;
