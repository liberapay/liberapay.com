-------------------------------------------------------------------------------
-- https://github.com/gittip/www.gittip.com/issues/449

CREATE INDEX username_index ON participants USING gin(username);
