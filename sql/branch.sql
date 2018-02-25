BEGIN;

    CREATE FUNCTION make_currency_basket(currency_amount) RETURNS currency_basket AS $$
        BEGIN RETURN (CASE
            WHEN $1.currency = 'EUR' THEN ($1.amount, '0.00')
                                     ELSE ('0.00', $1.amount)
        END); END;
    $$ LANGUAGE plpgsql IMMUTABLE STRICT;

    CREATE CAST (currency_amount as currency_basket) WITH FUNCTION make_currency_basket(currency_amount);

    CREATE FUNCTION make_currency_basket_or_null(currency_amount) RETURNS currency_basket AS $$
        BEGIN RETURN (CASE WHEN $1.amount = 0 THEN NULL ELSE make_currency_basket($1) END); END;
    $$ LANGUAGE plpgsql IMMUTABLE STRICT;

    ALTER TABLE participants
        DROP CONSTRAINT participants_leftover_check,
        ALTER COLUMN leftover DROP NOT NULL,
        ALTER COLUMN leftover TYPE currency_basket USING make_currency_basket_or_null(leftover);

    DROP FUNCTION make_currency_basket_or_null(currency_amount);

    DROP VIEW current_takes;

    ALTER TABLE takes
        ALTER COLUMN actual_amount TYPE currency_basket USING actual_amount::currency_basket;

    CREATE VIEW current_takes AS
        SELECT * FROM (
             SELECT DISTINCT ON (member, team) t.*
               FROM takes t
           ORDER BY member, team, mtime DESC
        ) AS anon WHERE amount IS NOT NULL;

    CREATE OR REPLACE FUNCTION initialize_amounts() RETURNS trigger AS $$
        BEGIN
            NEW.giving = coalesce_currency_amount(NEW.giving, NEW.main_currency);
            NEW.receiving = coalesce_currency_amount(NEW.receiving, NEW.main_currency);
            NEW.taking = coalesce_currency_amount(NEW.taking, NEW.main_currency);
            NEW.balance = coalesce_currency_amount(NEW.balance, NEW.main_currency);
            RETURN NEW;
        END;
    $$ LANGUAGE plpgsql;

    CREATE AGGREGATE sum(currency_basket) (
        sfunc = currency_basket_add,
        stype = currency_basket,
        initcond = '(0.00,0.00)'
    );

    CREATE FUNCTION empty_currency_basket() RETURNS currency_basket AS $$
        BEGIN RETURN ('0.00'::numeric, '0.00'::numeric); END;
    $$ LANGUAGE plpgsql IMMUTABLE;

END;
