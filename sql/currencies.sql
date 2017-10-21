-- Base types

CREATE TYPE currency AS ENUM ('EUR', 'USD');
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


-- Aggregate functions

CREATE AGGREGATE sum(currency_amount) (
    sfunc = currency_amount_add,
    stype = currency_amount
);


-- Convenience functions

CREATE FUNCTION get_currency(currency_amount) RETURNS currency AS $$
    BEGIN RETURN $1.currency; END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE CAST (currency_amount as currency) WITH FUNCTION get_currency(currency_amount);

CREATE FUNCTION zero(currency_amount) RETURNS currency_amount AS $$
    BEGIN RETURN ('0.00'::numeric, $1.currency); END;
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

CREATE TYPE currency_basket AS (EUR numeric, USD numeric);

CREATE FUNCTION currency_basket_add(currency_basket, currency_amount)
RETURNS currency_basket AS $$
    BEGIN
        IF ($2.currency = 'EUR') THEN
            RETURN ($1.EUR + $2.amount, $1.USD);
        ELSIF ($2.currency = 'USD') THEN
            RETURN ($1.EUR, $1.USD + $2.amount);
        ELSE
            RAISE 'unknown currency %', $2.currency;
        END IF;
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
    BEGIN RETURN ($1.EUR + $2.EUR, $1.USD + $2.USD); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR + (
    leftarg = currency_basket,
    rightarg = currency_basket,
    procedure = currency_basket_add,
    commutator = +
);

CREATE FUNCTION currency_basket_sub(currency_basket, currency_amount)
RETURNS currency_basket AS $$
    BEGIN
        IF ($2.currency = 'EUR') THEN
            RETURN ($1.EUR - $2.amount, $1.USD);
        ELSIF ($2.currency = 'USD') THEN
            RETURN ($1.EUR, $1.USD - $2.amount);
        ELSE
            RAISE 'unknown currency %', $2.currency;
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR - (
    leftarg = currency_basket,
    rightarg = currency_amount,
    procedure = currency_basket_sub
);

CREATE FUNCTION currency_basket_sub(currency_basket, currency_basket)
RETURNS currency_basket AS $$
    BEGIN RETURN ($1.EUR - $2.EUR, $1.USD - $2.USD); END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR - (
    leftarg = currency_basket,
    rightarg = currency_basket,
    procedure = currency_basket_sub
);

CREATE FUNCTION currency_basket_contains(currency_basket, currency_amount)
RETURNS boolean AS $$
    BEGIN
        IF ($2.currency = 'EUR') THEN
            RETURN ($1.EUR >= $2.amount);
        ELSIF ($2.currency = 'USD') THEN
            RETURN ($1.USD >= $2.amount);
        ELSE
            RAISE 'unknown currency %', $2.currency;
        END IF;
    END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;

CREATE OPERATOR >= (
    leftarg = currency_basket,
    rightarg = currency_amount,
    procedure = currency_basket_contains
);

CREATE AGGREGATE basket_sum(currency_amount) (
    sfunc = currency_basket_add,
    stype = currency_basket,
    initcond = '(0.00,0.00)'
);


-- Exchange rates

CREATE TABLE currency_exchange_rates
( source_currency   currency   NOT NULL
, target_currency   currency   NOT NULL
, rate              numeric    NOT NULL
, UNIQUE (source_currency, target_currency)
);


-- Currency conversion function

CREATE FUNCTION convert(currency_amount, currency) RETURNS currency_amount AS $$
    DECLARE
        rate numeric;
    BEGIN
        IF ($1.currency = $2) THEN RETURN $1; END IF;
        rate := (
            SELECT r.rate
              FROM currency_exchange_rates r
             WHERE r.source_currency = $1.currency
        );
        IF (rate IS NULL) THEN
            RAISE 'missing exchange rate %->%', $1.currency, $2;
        END IF;
        RETURN ($1.amount / rate, $2);
    END;
$$ LANGUAGE plpgsql STRICT;


-- Fuzzy sum of amounts in various currencies

CREATE FUNCTION currency_amount_fuzzy_sum_sfunc(
    currency_amount, currency_amount, currency
) RETURNS currency_amount AS $$
    BEGIN RETURN ($1.amount + (convert($2, $3)).amount, $3); END;
$$ LANGUAGE plpgsql STRICT;

CREATE AGGREGATE sum(currency_amount, currency) (
    sfunc = currency_amount_fuzzy_sum_sfunc,
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
        RETURN ($1._sum + (convert($2, $3)).amount, $1._count + 1, $3);
    END;
$$ LANGUAGE plpgsql STRICT;

CREATE FUNCTION currency_amount_fuzzy_avg_ffunc(currency_amount_fuzzy_avg_state)
RETURNS currency_amount AS $$
    BEGIN RETURN ((CASE WHEN $1._count = 0 THEN 0 ELSE $1._sum / $1._count END), $1.target); END;
$$ LANGUAGE plpgsql STRICT;

CREATE AGGREGATE avg(currency_amount, currency) (
    sfunc = currency_amount_fuzzy_avg_sfunc,
    finalfunc = currency_amount_fuzzy_avg_ffunc,
    stype = currency_amount_fuzzy_avg_state,
    initcond = '(0,0,)'
);
