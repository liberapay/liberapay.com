-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/pull/2172

BEGIN;
    ALTER TABLE homepage_top_receivers ADD COLUMN statement text;
    ALTER TABLE homepage_top_receivers ADD COLUMN number text;

    ALTER TABLE homepage_top_givers ADD COLUMN statement text;
    ALTER TABLE homepage_top_givers ADD COLUMN number text;
END;
