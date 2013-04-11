-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/503

BEGIN;

    ALTER TABLE participants ADD COLUMN username_lower text
       NOT NULL DEFAULT '';

    UPDATE participants SET username_lower = lower(username);

END;

ALTER TABLE participants ADD UNIQUE (username_lower);
