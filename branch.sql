-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/503

BEGIN;

    ALTER TABLE participants ADD COLUMN username_lowercased text
       NOT NULL DEFAULT '';

    UPDATE participants SET username_lowercased = lower(username);

END;

--ALTER TABLE participants ADD UNIQUE (username_lowercased);
