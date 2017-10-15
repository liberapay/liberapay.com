BEGIN;
    \i sql/currencies.sql
END;

ALTER TABLE participants ADD COLUMN main_currency currency NOT NULL DEFAULT 'EUR';
ALTER TABLE participants ADD COLUMN accept_all_currencies boolean NOT NULL DEFAULT FALSE;

BEGIN;
    ALTER TABLE cash_bundles ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
    ALTER TABLE debts ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
    ALTER TABLE exchanges ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
    ALTER TABLE exchanges ALTER COLUMN fee TYPE currency_amount USING (fee, 'EUR');
    ALTER TABLE exchanges ALTER COLUMN vat TYPE currency_amount USING (vat, 'EUR');
    ALTER TABLE transfers ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
END;

BEGIN;
    DROP VIEW current_tips;
    ALTER TABLE tips ALTER COLUMN amount TYPE currency_amount USING (amount, 'EUR');
    ALTER TABLE tips ALTER COLUMN periodic_amount TYPE currency_amount USING (periodic_amount, 'EUR');
    CREATE VIEW current_tips AS
        SELECT DISTINCT ON (tipper, tippee) *
          FROM tips
      ORDER BY tipper, tippee, mtime DESC;
END;

CREATE FUNCTION EUR(numeric) RETURNS currency_amount AS $$
    BEGIN RETURN ($1, 'EUR'); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

BEGIN;
    DROP VIEW sponsors;
    ALTER TABLE participants
        ALTER COLUMN goal DROP DEFAULT,
        ALTER COLUMN goal TYPE currency_amount USING EUR(goal),
        ALTER COLUMN goal SET DEFAULT NULL;
    ALTER TABLE participants
        ALTER COLUMN giving DROP DEFAULT,
        ALTER COLUMN giving TYPE currency_amount USING EUR(giving),
        ALTER COLUMN giving SET DEFAULT ('0.00', 'EUR');
    ALTER TABLE participants
        ALTER COLUMN receiving DROP DEFAULT,
        ALTER COLUMN receiving TYPE currency_amount USING EUR(receiving),
        ALTER COLUMN receiving SET DEFAULT ('0.00', 'EUR');
    ALTER TABLE participants
        ALTER COLUMN taking DROP DEFAULT,
        ALTER COLUMN taking TYPE currency_amount USING EUR(taking),
        ALTER COLUMN taking SET DEFAULT ('0.00', 'EUR');
    ALTER TABLE participants
        ALTER COLUMN leftover DROP DEFAULT,
        ALTER COLUMN leftover TYPE currency_amount USING EUR(leftover),
        ALTER COLUMN leftover SET DEFAULT ('0.00', 'EUR');
    CREATE VIEW sponsors AS
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

DROP FUNCTION EUR(numeric);
