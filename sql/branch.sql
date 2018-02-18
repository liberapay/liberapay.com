BEGIN;
    ALTER TABLE participants ADD COLUMN accepted_currencies text;

    UPDATE participants
       SET accepted_currencies = (
               CASE WHEN accept_all_currencies THEN 'EUR,USD' ELSE main_currency::text END
           )
     WHERE accept_all_currencies IS NOT NULL;
END;

SELECT 'after deployment';

BEGIN;
    UPDATE participants
       SET accepted_currencies = (
               CASE WHEN accept_all_currencies THEN 'EUR,USD' ELSE main_currency::text END
           )
     WHERE accept_all_currencies IS NOT NULL
       AND accepted_currencies <> (
               CASE WHEN accept_all_currencies THEN 'EUR,USD' ELSE main_currency::text END
           );

    DROP VIEW sponsors;
    CREATE OR REPLACE VIEW sponsors AS
        SELECT username, giving, avatar_url
          FROM participants p
         WHERE status = 'active'
           AND kind = 'organization'
           AND giving > receiving
           AND giving >= 10
           AND hide_from_lists = 0
           AND profile_noindex = 0
        ;

    ALTER TABLE participants DROP COLUMN accept_all_currencies;
END;
