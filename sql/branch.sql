CREATE OR REPLACE FUNCTION empty_currency_basket() RETURNS currency_basket AS $$
    BEGIN RETURN (0::numeric,0::numeric,jsonb_build_object()); END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION coalesce_currency_basket(currency_basket) RETURNS currency_basket AS $$
    BEGIN
        IF ($1 IS NULL) THEN
            RETURN empty_currency_basket();
        END IF;
        IF (coalesce($1.EUR, 0) <> 0 OR coalesce($1.USD, 0) <> 0) THEN
            IF (jsonb_typeof($1.amounts) = 'object') THEN
                RAISE 'got an hybrid currency basket: %', $1;
            END IF;
            RETURN _wrap_amounts(jsonb_build_object(
                'EUR', coalesce($1.EUR, 0)::text,
                'USD', coalesce($1.USD, 0)::text
            ));
        ELSIF (jsonb_typeof($1.amounts) = 'object') THEN
            IF ($1.EUR IS NULL OR $1.USD IS NULL) THEN
                RETURN (0::numeric,0::numeric,$1.amounts);
            END IF;
            RETURN $1;
        ELSIF ($1.amounts IS NULL OR jsonb_typeof($1.amounts) <> 'null') THEN
            RETURN (0::numeric,0::numeric,jsonb_build_object());
        ELSE
            RAISE 'unexpected JSON type: %', jsonb_typeof($1.amounts);
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION _wrap_amounts(jsonb) RETURNS currency_basket AS $$
    BEGIN
        IF ($1 IS NULL) THEN
            RETURN (0::numeric,0::numeric,jsonb_build_object());
        ELSE
            RETURN (0::numeric,0::numeric,$1);
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION make_currency_basket(currency_amount) RETURNS currency_basket AS $$
    BEGIN RETURN (0::numeric,0::numeric,jsonb_build_object($1.currency::text, $1.amount::text)); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
