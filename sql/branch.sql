BEGIN;
    ALTER TABLE tips ADD COLUMN visibility int CHECK (visibility >= -3 AND visibility <> 0 AND visibility <= 3);
    -- 1 means secret, 2 means private, 3 means public, negative numbers mean hidden
    ALTER TABLE payin_transfers ADD COLUMN visibility int DEFAULT 1 CHECK (visibility >= 1 AND visibility <= 3);
    -- same meanings as for tips, but negative numbers aren't allowed

    UPDATE tips SET visibility = -1 WHERE hidden AND visibility IS NULL;

    CREATE OR REPLACE VIEW current_tips AS
        SELECT DISTINCT ON (tipper, tippee) *
          FROM tips
      ORDER BY tipper, tippee, mtime DESC;

    CREATE TABLE recipient_settings
    ( participant           bigint   PRIMARY KEY REFERENCES participants
    , patron_visibilities   int      NOT NULL CHECK (patron_visibilities > 0)
    -- Three bits: 1 is for "secret", 2 is for "private", 4 is for "public".
    );
END;

SELECT 'after deployment';

BEGIN;
    UPDATE tips SET visibility = -1 WHERE hidden AND visibility = 1;
    DROP FUNCTION compute_arrears(current_tips);
    DROP CAST (current_tips AS tips);
    DROP VIEW current_tips;
    ALTER TABLE tips
        DROP COLUMN hidden,
        ALTER COLUMN visibility DROP DEFAULT,
        ALTER COLUMN visibility SET NOT NULL;
    CREATE OR REPLACE VIEW current_tips AS
        SELECT DISTINCT ON (tipper, tippee) *
          FROM tips
      ORDER BY tipper, tippee, mtime DESC;
    CREATE CAST (current_tips AS tips) WITH INOUT;
    CREATE FUNCTION compute_arrears(tip current_tips) RETURNS currency_amount AS $$
        SELECT compute_arrears(tip::tips);
    $$ LANGUAGE sql;
    ALTER TABLE payin_transfers
        ALTER COLUMN visibility DROP DEFAULT,
        ALTER COLUMN visibility SET NOT NULL;
END;
