-- The list below is from https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml
-- It includes all the settlement currencies currently supported by Stripe: https://stripe.com/docs/currencies
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'AUD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BGN';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BRL';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'CAD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'CHF';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'CNY';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'CZK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'DKK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'GBP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'HKD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'HRK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'HUF';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'IDR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'ILS';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'INR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'ISK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'JPY';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'KRW';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MXN';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'MYR';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'NOK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'NZD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'PHP';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'PLN';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'RON';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'RUB';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'SEK';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'SGD';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'THB';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'TRY';
ALTER TYPE currency ADD VALUE IF NOT EXISTS 'ZAR';


-- https://en.wikipedia.org/wiki/ISO_4217
CREATE FUNCTION get_currency_exponent(currency) RETURNS int AS $$
    BEGIN RETURN (CASE
        WHEN $1 IN ('ISK', 'JPY', 'KRW') THEN 0 ELSE 2
    END); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;


CREATE OR REPLACE FUNCTION coalesce_currency_amount(currency_amount, currency) RETURNS currency_amount AS $$
    DECLARE
        c currency := COALESCE($1.currency, $2);
    BEGIN
        RETURN (COALESCE($1.amount, round(0, get_currency_exponent(c))), c);
    END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION round(currency_amount) RETURNS currency_amount AS $$
    BEGIN RETURN (round($1.amount, get_currency_exponent($1.currency)), $1.currency); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OR REPLACE FUNCTION zero(currency) RETURNS currency_amount AS $$
    BEGIN RETURN (round(0, get_currency_exponent($1)), $1); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OR REPLACE FUNCTION zero(currency_amount) RETURNS currency_amount AS $$
    BEGIN RETURN (round(0, get_currency_exponent($1.currency)), $1.currency); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OR REPLACE FUNCTION convert(currency_amount, currency, boolean) RETURNS currency_amount AS $$
    DECLARE
        rate numeric;
        result currency_amount;
    BEGIN
        IF ($1.currency = $2) THEN RETURN $1; END IF;
        IF ($1.currency = 'EUR' OR $2 = 'EUR') THEN
            rate := (
                SELECT r.rate
                  FROM currency_exchange_rates r
                 WHERE r.source_currency = $1.currency
                   AND r.target_currency = $2
            );
        ELSE
            rate := (
                SELECT r.rate
                  FROM currency_exchange_rates r
                 WHERE r.source_currency = $1.currency
                   AND r.target_currency = 'EUR'
            ) * (
                SELECT r.rate
                  FROM currency_exchange_rates r
                 WHERE r.source_currency = 'EUR'
                   AND r.target_currency = $2
            );
        END IF;
        IF (rate IS NULL) THEN
            RAISE 'missing exchange rate %->%', $1.currency, $2;
        END IF;
        result := ($1.amount * rate, $2);
        RETURN (CASE WHEN $3 THEN round(result) ELSE result END);
    END;
$$ LANGUAGE plpgsql STRICT;
