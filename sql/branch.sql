CREATE FUNCTION _wrap_amounts(jsonb) RETURNS currency_basket AS $$
    BEGIN
        IF ($1 IS NULL) THEN
            RETURN (NULL::numeric,NULL::numeric);
        ELSE
            RETURN (($1->>'EUR')::numeric, ($1->>'USD')::numeric);
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE;

SELECT 'after deployment';

BEGIN;

    ALTER TYPE currency_basket ADD ATTRIBUTE amounts jsonb;

    CREATE OR REPLACE FUNCTION empty_currency_basket() RETURNS currency_basket AS $$
        BEGIN RETURN (NULL::numeric,NULL::numeric,jsonb_build_object()); END;
    $$ LANGUAGE plpgsql;

    CREATE FUNCTION coalesce_currency_basket(currency_basket) RETURNS currency_basket AS $$
        BEGIN
            IF (coalesce($1.EUR, 0) > 0 OR coalesce($1.USD, 0) > 0) THEN
                IF ($1.amounts ? 'EUR' OR $1.amounts ? 'USD') THEN
                    RAISE 'got an hybrid currency basket: %', $1;
                END IF;
                RETURN _wrap_amounts(
                    jsonb_build_object('EUR', $1.EUR::text, 'USD', $1.USD::text)
                );
            ELSIF (jsonb_typeof($1.amounts) = 'object') THEN
                RETURN $1;
            ELSIF ($1.amounts IS NULL OR jsonb_typeof($1.amounts) <> 'null') THEN
                RETURN (NULL::numeric,NULL::numeric,jsonb_build_object());
            ELSE
                RAISE 'unexpected JSON type: %', jsonb_typeof($1.amounts);
            END IF;
        END;
    $$ LANGUAGE plpgsql IMMUTABLE;

    CREATE OR REPLACE FUNCTION _wrap_amounts(jsonb) RETURNS currency_basket AS $$
        BEGIN
            IF ($1 IS NULL) THEN
                RETURN (NULL::numeric,NULL::numeric,jsonb_build_object());
            ELSE
                RETURN (NULL::numeric,NULL::numeric,$1);
            END IF;
        END;
    $$ LANGUAGE plpgsql IMMUTABLE;

    CREATE OR REPLACE FUNCTION make_currency_basket(currency_amount) RETURNS currency_basket AS $$
        BEGIN RETURN (NULL::numeric,NULL::numeric,jsonb_build_object($1.currency::text, $1.amount::text)); END;
    $$ LANGUAGE plpgsql IMMUTABLE STRICT;

    CREATE OR REPLACE FUNCTION currency_basket_add(currency_basket, currency_amount)
    RETURNS currency_basket AS $$
        DECLARE
            r currency_basket;
        BEGIN
            r := coalesce_currency_basket($1);
            IF ($2.amount IS NULL OR $2.amount = 0 OR $2.currency IS NULL) THEN
                RETURN r;
            END IF;
            r.amounts := jsonb_set(
                r.amounts,
                string_to_array($2.currency::text, ' '),
                (coalesce((r.amounts->>$2.currency::text)::numeric, 0) + $2.amount)::text::jsonb
            );
            RETURN r;
        END;
    $$ LANGUAGE plpgsql IMMUTABLE STRICT;

    CREATE OR REPLACE FUNCTION currency_basket_add(currency_basket, currency_basket)
    RETURNS currency_basket AS $$
        DECLARE
            amounts1 jsonb;
            amounts2 jsonb;
            currency text;
        BEGIN
            amounts1 := (coalesce_currency_basket($1)).amounts;
            amounts2 := (coalesce_currency_basket($2)).amounts;
            FOR currency IN SELECT * FROM jsonb_object_keys(amounts2) LOOP
                amounts1 := jsonb_set(
                    amounts1,
                    string_to_array(currency, ' '),
                    ( coalesce((amounts1->>currency)::numeric, 0) +
                      coalesce((amounts2->>currency)::numeric, 0)
                    )::text::jsonb
                );
            END LOOP;
            RETURN _wrap_amounts(amounts1);
        END;
    $$ LANGUAGE plpgsql IMMUTABLE STRICT;

    CREATE OR REPLACE FUNCTION currency_basket_sub(currency_basket, currency_amount)
    RETURNS currency_basket AS $$
        BEGIN RETURN currency_basket_add($1, -$2); END;
    $$ LANGUAGE plpgsql IMMUTABLE STRICT;

    CREATE OR REPLACE FUNCTION currency_basket_sub(currency_basket, currency_basket)
    RETURNS currency_basket AS $$
        DECLARE
            amounts1 jsonb;
            amounts2 jsonb;
            currency text;
        BEGIN
            amounts1 := (coalesce_currency_basket($1)).amounts;
            amounts2 := (coalesce_currency_basket($2)).amounts;
            FOR currency IN SELECT * FROM jsonb_object_keys(amounts2) LOOP
                amounts1 := jsonb_set(
                    amounts1,
                    string_to_array(currency, ' '),
                    ( coalesce((amounts1->>currency)::numeric, 0) -
                      coalesce((amounts2->>currency)::numeric, 0)
                    )::text::jsonb
                );
            END LOOP;
            RETURN _wrap_amounts(amounts1);
        END;
    $$ LANGUAGE plpgsql IMMUTABLE STRICT;

    CREATE OR REPLACE FUNCTION currency_basket_contains(currency_basket, currency_amount)
    RETURNS boolean AS $$
        BEGIN RETURN coalesce(coalesce_currency_basket($1)->$2.currency::text, 0) >= $2.amount; END;
    $$ LANGUAGE plpgsql IMMUTABLE STRICT;

    DROP AGGREGATE basket_sum(currency_amount);
    CREATE AGGREGATE basket_sum(currency_amount) (
        sfunc = currency_basket_add,
        stype = currency_basket,
        initcond = '(,,{})'
    );

    DROP AGGREGATE sum(currency_basket);
    CREATE AGGREGATE sum(currency_basket) (
        sfunc = currency_basket_add,
        stype = currency_basket,
        initcond = '(,,{})'
    );

    CREATE FUNCTION get_amount_from_currency_basket(currency_basket, currency)
    RETURNS numeric AS $$
        BEGIN RETURN (coalesce_currency_basket($1)).amounts->>$2::text; END;
    $$ LANGUAGE plpgsql IMMUTABLE STRICT;

    CREATE FUNCTION get_amount_from_currency_basket(currency_basket, text)
    RETURNS numeric AS $$
        BEGIN RETURN (coalesce_currency_basket($1)).amounts->>$2; END;
    $$ LANGUAGE plpgsql IMMUTABLE STRICT;

    CREATE OPERATOR -> (
        leftarg = currency_basket,
        rightarg = currency,
        procedure = get_amount_from_currency_basket
    );

    CREATE OPERATOR -> (
        leftarg = currency_basket,
        rightarg = text,
        procedure = get_amount_from_currency_basket
    );

    ALTER TABLE paydays ALTER COLUMN transfer_volume           SET DEFAULT empty_currency_basket();
    ALTER TABLE paydays ALTER COLUMN take_volume               SET DEFAULT empty_currency_basket();
    ALTER TABLE paydays ALTER COLUMN week_deposits             SET DEFAULT empty_currency_basket();
    ALTER TABLE paydays ALTER COLUMN week_withdrawals          SET DEFAULT empty_currency_basket();
    ALTER TABLE paydays ALTER COLUMN transfer_volume_refunded  SET DEFAULT empty_currency_basket();
    ALTER TABLE paydays ALTER COLUMN week_deposits_refunded    SET DEFAULT empty_currency_basket();
    ALTER TABLE paydays ALTER COLUMN week_withdrawals_refunded SET DEFAULT empty_currency_basket();

    UPDATE participants
       SET accepted_currencies = NULL
     WHERE status = 'stub'
       AND accepted_currencies IS NOT NULL;

END;
