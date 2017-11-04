BEGIN;
    CREATE FUNCTION coalesce_currency_amount(currency_amount, currency) RETURNS currency_amount AS $$
        BEGIN RETURN (COALESCE($1.amount, '0.00'::numeric), COALESCE($1.currency, $2)); END;
    $$ LANGUAGE plpgsql IMMUTABLE;
    CREATE OR REPLACE FUNCTION initialize_amounts() RETURNS trigger AS $$
        BEGIN
            NEW.giving = coalesce_currency_amount(NEW.giving, NEW.main_currency);
            NEW.receiving = coalesce_currency_amount(NEW.receiving, NEW.main_currency);
            NEW.taking = coalesce_currency_amount(NEW.taking, NEW.main_currency);
            NEW.leftover = coalesce_currency_amount(NEW.leftover, NEW.main_currency);
            NEW.balance = coalesce_currency_amount(NEW.balance, NEW.main_currency);
            RETURN NEW;
        END;
    $$ LANGUAGE plpgsql;
    DROP TRIGGER initialize_amounts ON participants;
    CREATE TRIGGER initialize_amounts
        BEFORE INSERT OR UPDATE ON participants
        FOR EACH ROW EXECUTE PROCEDURE initialize_amounts();
END;
