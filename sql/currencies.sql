-- Base types

-- The list below is from https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml
-- It includes all the settlement currencies currently supported by Stripe: https://stripe.com/docs/currencies
CREATE TYPE currency AS ENUM (
    'EUR', 'USD',
    'AUD', 'BGN', 'BRL', 'CAD', 'CHF', 'CNY', 'CZK', 'DKK', 'GBP', 'HKD', 'HRK',
    'HUF', 'IDR', 'ILS', 'INR', 'ISK', 'JPY', 'KRW', 'MXN', 'MYR', 'NOK', 'NZD',
    'PHP', 'PLN', 'RON', 'RUB', 'SEK', 'SGD', 'THB', 'TRY', 'ZAR',
    'AED', 'AFN', 'ALL', 'AMD', 'ANG', 'AOA', 'ARS', 'AWG', 'AZN', 'BAM', 'BBD',
    'BDT', 'BIF', 'BMD', 'BND', 'BOB', 'BSD', 'BWP', 'BYN', 'BZD', 'CDF', 'CLP',
    'COP', 'CRC', 'CVE', 'DJF', 'DOP', 'DZD', 'EGP', 'ETB', 'FJD', 'FKP', 'GEL',
    'GIP', 'GMD', 'GNF', 'GTQ', 'GYD', 'HNL', 'HTG', 'JMD', 'KES', 'KGS', 'KHR',
    'KMF', 'KYD', 'KZT', 'LAK', 'LBP', 'LKR', 'LRD', 'LSL', 'MAD', 'MDL', 'MGA',
    'MKD', 'MMK', 'MNT', 'MOP', 'MUR', 'MVR', 'MWK', 'MZN', 'NAD', 'NGN', 'NIO',
    'NPR', 'PAB', 'PEN', 'PGK', 'PKR', 'PYG', 'QAR', 'RSD', 'RWF', 'SAR', 'SBD',
    'SCR', 'SHP', 'SLE', 'SOS', 'SRD', 'SZL', 'TJS', 'TOP', 'TTD', 'TWD', 'TZS',
    'UAH', 'UGX', 'UYU', 'UZS', 'VND', 'VUV', 'WST', 'XAF', 'XCD', 'XOF', 'XPF',
    'YER', 'ZMW'
);
CREATE TYPE currency_amount AS (amount numeric, currency currency);


-- Arithmetic operators

CREATE FUNCTION currency_amount_add(currency_amount, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount + $2.amount, $1.currency);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR + (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_add,
    commutator = +
);

CREATE FUNCTION currency_amount_sub(currency_amount, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount - $2.amount, $1.currency);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR - (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_sub
);

CREATE FUNCTION currency_amount_neg(currency_amount)
RETURNS currency_amount AS $$
    BEGIN RETURN (-$1.amount, $1.currency); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR - (
    rightarg = currency_amount,
    procedure = currency_amount_neg
);

CREATE FUNCTION currency_amount_mul(currency_amount, numeric)
RETURNS currency_amount AS $$
    BEGIN
        RETURN ($1.amount * $2, $1.currency);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR * (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_mul,
    commutator = *
);

CREATE FUNCTION currency_amount_mul(numeric, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        RETURN ($2.amount * $1, $2.currency);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR * (
    leftarg = numeric,
    rightarg = currency_amount,
    procedure = currency_amount_mul,
    commutator = *
);

CREATE FUNCTION currency_amount_div(currency_amount, currency_amount)
RETURNS numeric AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN $1.amount / $2.amount;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR / (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_div
);


-- Aggregate functions

CREATE FUNCTION max(currency_amount, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        IF ($2.amount > $1.amount) THEN
            RETURN $2;
        ELSE
            RETURN $1;
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE AGGREGATE max(currency_amount) (
    sfunc = max,
    stype = currency_amount
);

CREATE FUNCTION min(currency_amount, currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        IF ($2.amount < $1.amount) THEN
            RETURN $2;
        ELSE
            RETURN $1;
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE AGGREGATE min(currency_amount) (
    sfunc = min,
    stype = currency_amount
);

CREATE AGGREGATE sum(currency_amount) (
    sfunc = currency_amount_add,
    stype = currency_amount
);


-- Convenience functions

-- https://en.wikipedia.org/wiki/ISO_4217
CREATE FUNCTION get_currency_exponent(currency) RETURNS int AS $$
    BEGIN RETURN (CASE
        WHEN $1 IN ('ISK', 'JPY', 'KRW') THEN 0 ELSE 2
    END); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE FUNCTION coalesce_currency_amount(currency_amount, currency) RETURNS currency_amount AS $$
    DECLARE
        c currency := COALESCE($1.currency, $2);
    BEGIN
        RETURN (COALESCE($1.amount, round(0, get_currency_exponent(c))), c);
    END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE FUNCTION get_currency(currency_amount) RETURNS currency AS $$
    BEGIN RETURN $1.currency; END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE CAST (currency_amount as currency) WITH FUNCTION get_currency(currency_amount);

CREATE FUNCTION round(currency_amount) RETURNS currency_amount AS $$
    BEGIN RETURN (round($1.amount, get_currency_exponent($1.currency)), $1.currency); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE FUNCTION zero(currency) RETURNS currency_amount AS $$
    BEGIN RETURN (round(0, get_currency_exponent($1)), $1); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE FUNCTION zero(currency_amount) RETURNS currency_amount AS $$
    BEGIN RETURN (round(0, get_currency_exponent($1.currency)), $1.currency); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;


-- Comparison operators

CREATE FUNCTION currency_amount_eq(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN RETURN ($1.currency = $2.currency AND $1.amount = $2.amount); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR = (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_eq,
    commutator = =
);

CREATE FUNCTION currency_amount_ne(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN RETURN ($1.currency <> $2.currency OR $1.amount <> $2.amount); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR <> (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_ne,
    commutator = <>
);

CREATE FUNCTION currency_amount_gt(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount > $2.amount);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR > (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_gt,
    commutator = <,
    negator = <=
);

CREATE FUNCTION currency_amount_gte(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount >= $2.amount);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR >= (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_gte,
    commutator = <=,
    negator = <
);

CREATE FUNCTION currency_amount_lt(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount < $2.amount);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR < (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_lt,
    commutator = >,
    negator = >=
);

CREATE FUNCTION currency_amount_lte(currency_amount, currency_amount)
RETURNS boolean AS $$
    BEGIN
        IF ($1.currency <> $2.currency) THEN
            RAISE 'currency mistmatch: % != %', $1.currency, $2.currency;
        END IF;
        RETURN ($1.amount <= $2.amount);
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR <= (
    leftarg = currency_amount,
    rightarg = currency_amount,
    procedure = currency_amount_lte,
    commutator = >=,
    negator = >
);

CREATE FUNCTION currency_amount_eq_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount = $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR = (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_eq_numeric,
    commutator = =
);

CREATE FUNCTION currency_amount_ne_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount <> $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR <> (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_ne_numeric,
    commutator = <>
);

CREATE FUNCTION currency_amount_gt_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount > $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR > (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_gt_numeric,
    commutator = <,
    negator = <=
);

CREATE FUNCTION currency_amount_gte_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount >= $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR >= (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_gte_numeric,
    commutator = <=,
    negator = <
);

CREATE FUNCTION currency_amount_lt_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount < $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR < (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_lt_numeric,
    commutator = >,
    negator = >=
);

CREATE FUNCTION currency_amount_lte_numeric(currency_amount, numeric)
RETURNS boolean AS $$
    BEGIN RETURN ($1.amount <= $2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR <= (
    leftarg = currency_amount,
    rightarg = numeric,
    procedure = currency_amount_lte_numeric,
    commutator = >=,
    negator = >
);


-- Basket type: amounts in multiple currencies

CREATE TYPE currency_basket AS (EUR numeric, USD numeric, amounts jsonb);

CREATE FUNCTION empty_currency_basket() RETURNS currency_basket AS $$
    BEGIN RETURN (0::numeric,0::numeric,jsonb_build_object()); END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION coalesce_currency_basket(currency_basket) RETURNS currency_basket AS $$
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

CREATE FUNCTION _wrap_amounts(jsonb) RETURNS currency_basket AS $$
    BEGIN
        IF ($1 IS NULL) THEN
            RETURN (0::numeric,0::numeric,jsonb_build_object());
        ELSE
            RETURN (0::numeric,0::numeric,$1);
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE FUNCTION make_currency_basket(currency_amount) RETURNS currency_basket AS $$
    BEGIN RETURN (0::numeric,0::numeric,jsonb_build_object($1.currency::text, $1.amount::text)); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE CAST (currency_amount as currency_basket) WITH FUNCTION make_currency_basket(currency_amount);

CREATE FUNCTION currency_basket_add(currency_basket, currency_amount)
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

CREATE OPERATOR + (
    leftarg = currency_basket,
    rightarg = currency_amount,
    procedure = currency_basket_add,
    commutator = +
);

CREATE FUNCTION currency_basket_add(currency_basket, currency_basket)
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

CREATE OPERATOR + (
    leftarg = currency_basket,
    rightarg = currency_basket,
    procedure = currency_basket_add,
    commutator = +
);

CREATE FUNCTION currency_basket_sub(currency_basket, currency_amount)
RETURNS currency_basket AS $$
    BEGIN RETURN currency_basket_add($1, -$2); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR - (
    leftarg = currency_basket,
    rightarg = currency_amount,
    procedure = currency_basket_sub
);

CREATE FUNCTION currency_basket_sub(currency_basket, currency_basket)
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

CREATE OPERATOR - (
    leftarg = currency_basket,
    rightarg = currency_basket,
    procedure = currency_basket_sub
);

CREATE FUNCTION currency_basket_contains(currency_basket, currency_amount)
RETURNS boolean AS $$
    BEGIN RETURN coalesce(coalesce_currency_basket($1)->$2.currency::text, 0) >= $2.amount; END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR >= (
    leftarg = currency_basket,
    rightarg = currency_amount,
    procedure = currency_basket_contains
);

CREATE AGGREGATE basket_sum(currency_amount) (
    sfunc = currency_basket_add,
    stype = currency_basket,
    initcond = '(,,{})'
);

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


-- Exchange rates

CREATE TABLE currency_exchange_rates
( source_currency   currency   NOT NULL
, target_currency   currency   NOT NULL
, rate              numeric    NOT NULL
, UNIQUE (source_currency, target_currency)
);


-- Currency conversion function

CREATE FUNCTION convert(currency_amount, currency, boolean) RETURNS currency_amount AS $$
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

CREATE FUNCTION convert(currency_amount, currency) RETURNS currency_amount AS $$
    BEGIN RETURN convert($1, $2, true); END;
$$ LANGUAGE plpgsql STRICT;


-- Fuzzy sum of amounts in various currencies

CREATE FUNCTION currency_amount_fuzzy_sum_sfunc(
    currency_amount, currency_amount, currency
) RETURNS currency_amount AS $$
    BEGIN
        IF ($2.amount IS NULL OR $2.currency IS NULL) THEN RETURN $1; END IF;
        RETURN ($1.amount + (convert($2, $3, false)).amount, $3);
    END;
$$ LANGUAGE plpgsql STRICT;

CREATE FUNCTION currency_amount_fuzzy_sum_ffunc(currency_amount)
RETURNS currency_amount AS $$
    BEGIN
        IF ($1.amount IS NULL OR $1.currency IS NULL) THEN RETURN NULL; END IF;
        RETURN round($1);
    END;
$$ LANGUAGE plpgsql;

CREATE AGGREGATE sum(currency_amount, currency) (
    sfunc = currency_amount_fuzzy_sum_sfunc,
    finalfunc = currency_amount_fuzzy_sum_ffunc,
    stype = currency_amount,
    initcond = '(0,)'
);


-- Fuzzy average of amounts in various currencies

CREATE TYPE currency_amount_fuzzy_avg_state AS (
    _sum numeric, _count int, target currency
);

CREATE FUNCTION currency_amount_fuzzy_avg_sfunc(
    currency_amount_fuzzy_avg_state, currency_amount, currency
) RETURNS currency_amount_fuzzy_avg_state AS $$
    BEGIN
        IF ($2.currency = $3) THEN
            RETURN ($1._sum + $2.amount, $1._count + 1, $3);
        END IF;
        RETURN ($1._sum + (convert($2, $3, false)).amount, $1._count + 1, $3);
    END;
$$ LANGUAGE plpgsql STRICT;

CREATE FUNCTION currency_amount_fuzzy_avg_ffunc(currency_amount_fuzzy_avg_state)
RETURNS currency_amount AS $$
    BEGIN RETURN round(
        ((CASE WHEN $1._count = 0 THEN 0 ELSE $1._sum / $1._count END), $1.target)::currency_amount
    ); END;
$$ LANGUAGE plpgsql STRICT;

CREATE AGGREGATE avg(currency_amount, currency) (
    sfunc = currency_amount_fuzzy_avg_sfunc,
    finalfunc = currency_amount_fuzzy_avg_ffunc,
    stype = currency_amount_fuzzy_avg_state,
    initcond = '(0,0,)'
);
