BEGIN;

    LOCK TABLE participants IN EXCLUSIVE MODE;

    DROP VIEW sponsors;

    ALTER TABLE participants
        ALTER COLUMN profile_noindex DROP DEFAULT,
        ALTER COLUMN profile_noindex SET DATA TYPE int USING (profile_noindex::int | 2),
        ALTER COLUMN profile_noindex SET DEFAULT 2;

    ALTER TABLE participants
        ALTER COLUMN hide_from_lists DROP DEFAULT,
        ALTER COLUMN hide_from_lists SET DATA TYPE int USING (hide_from_lists::int),
        ALTER COLUMN hide_from_lists SET DEFAULT 0;

    ALTER TABLE participants
        ALTER COLUMN hide_from_search DROP DEFAULT,
        ALTER COLUMN hide_from_search SET DATA TYPE int USING (hide_from_search::int),
        ALTER COLUMN hide_from_search SET DEFAULT 0;

    CREATE OR REPLACE VIEW sponsors AS
        SELECT *
          FROM participants p
         WHERE status = 'active'
           AND kind = 'organization'
           AND giving > receiving
           AND giving >= 10
           AND hide_from_lists = 0
           AND profile_noindex = 0
        ;

END;

UPDATE participants SET profile_nofollow = true;
