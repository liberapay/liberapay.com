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
