DELETE FROM notifications WHERE event IN (
    'income',
    'once/mangopay-exodus',
    'withdrawal_created',
    'withdrawal_failed'
);

SELECT 'after deployment';

BEGIN;
    DELETE FROM app_conf WHERE key LIKE 'mangopay_%';
    DROP TABLE cash_bundles;
    DROP TRIGGER upsert_mangopay_user_id ON participants;
    DROP FUNCTION upsert_mangopay_user_id();
    DROP TABLE mangopay_users;
    CREATE OR REPLACE FUNCTION initialize_amounts() RETURNS trigger AS $$
        BEGIN
            NEW.giving = coalesce_currency_amount(NEW.giving, NEW.main_currency);
            NEW.receiving = coalesce_currency_amount(NEW.receiving, NEW.main_currency);
            NEW.taking = coalesce_currency_amount(NEW.taking, NEW.main_currency);
            RETURN NEW;
        END;
    $$ LANGUAGE plpgsql;
    ALTER TABLE participants DROP CONSTRAINT mangopay_chk;
    ALTER TABLE participants DROP COLUMN balance;
    ALTER TABLE participants DROP COLUMN mangopay_user_id;
END;
